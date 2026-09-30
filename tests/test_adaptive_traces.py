"""Captured proxy contract and public inventory-to-view boundary, offline only."""
import copy
import json
from pathlib import Path
from unittest import mock

from collector.coverage import Coverage
from collector.emit import hydrate
from collector.pillars import adaptive_traces, compose
from collector.sources import adaptive_traces as source

FIXTURE = Path(__file__).parent / "fixtures" / "adaptive_traces"
STACK = {"slug": "obs-hub", "url": "https://inventory.example", "regionSlug": "test-region"}


class Response:
    def __init__(self, body, status=200):
        self.body, self.status = body, status
        self.ok = status == 200

    def json(self):
        return self.body


class Proxy:
    def __init__(self, overrides=None):
        self.responses = {resource: Response(json.loads((FIXTURE / f"{resource}.json").read_text()))
                          for resource in ("config", "policies", "recommendations")}
        self.responses["health"] = Response({"message": "synthetic"}, 404)
        self.responses.update(overrides or {})
        self.calls = []

    def get(self, url, *, bearer):
        self.calls.append((url, bearer))
        response = self.responses[url.rsplit("/", 1)[-1]]
        if isinstance(response, Exception):
            raise response
        return response


def test_captured_proxy_to_compose_drops_content_and_emits_no_business_metrics():
    client = Proxy()
    inventory = source.probe_all(client, [STACK], {"obs-hub": {"token": "synthetic"},
                                                "departed": {"token": "unused"}})
    record = inventory["obs-hub"]
    assert list(inventory) == ["obs-hub"]
    assert record["health_state"] == "not_found_404"
    assert record["policy_count"] == 4
    assert record["policy_type_counts"] == {"status_code": 1, "latency": 1,
                                           "volumetric": 1, "diversity": 1, "other": 0}
    assert record["recommendation_count"] == 5
    assert record["pending_recommendation_count"] == 0
    assert client.calls[0][0] == f"https://inventory.example/{source.PATH}/health"
    assert all(url.startswith(f"https://inventory.example/{source.PATH}/") for url, _ in client.calls)
    assert all(token == "synthetic" for _, token in client.calls)
    cov = Coverage(tier="t2", total=1)
    cov.record_ok("obs-hub")
    baseline, _ = compose.build_all([STACK], cov)
    metrics, views = compose.build_all([STACK], cov, adaptive_traces=inventory)
    assert metrics == baseline
    row = views[adaptive_traces.VIEW][0]
    assert row["policy_count"] == 4 and row["config_available"] is True
    persisted = json.dumps([inventory, row])
    for field in ('"body"', '"name"', '"id"', '"message"', '"actions"', '"labels"',
                  '"seed"', '"version_created_by"'):
        assert field not in persisted


def test_pending_is_not_applied_dismissed_or_stale_and_types_are_bounded():
    client = Proxy()
    recommendations = client.responses["recommendations"].body
    for row, flags in zip(recommendations, [(False, False, False), (True, False, False),
                                          (False, True, False), (False, False, True),
                                          (True, True, True)]):
        row.update(zip(("applied", "dismissed", "stale"), flags))
    client.responses["policies"].body[0]["type"] = "private-policy-class"
    record = source.probe_stack(client, STACK, "synthetic")
    assert record["pending_recommendation_count"] == 1
    assert record["policy_type_counts"]["other"] == 1
    assert "private-policy-class" not in json.dumps(record)


def test_missing_domains_are_gaps_not_zero_and_health_is_not_a_resource_gate():
    for health in (404, 500):
        client = Proxy({"health": Response(None, health), "config": Response(None, 404),
                        "recommendations": Response({"unexpected": []})})
        record = source.probe_stack(client, STACK, "synthetic")
        assert record["available"] and record["policy_count"] == 4
        assert record["config_available"] is None
        assert "recommendation_count" not in record
        _, views = adaptive_traces.build([STACK], {"obs-hub": record})
        assert views[adaptive_traces.VIEW][0]["recommendation_count"] is None
    missing_flag = copy.deepcopy(Proxy().responses["recommendations"].body)
    del missing_flag[0]["stale"]
    record = source.probe_stack(Proxy({"recommendations": Response(missing_flag)}), STACK, "synthetic")
    assert record["recommendations_state"] == "invalid_response"
    assert "pending_recommendation_count" not in record
    client = Proxy({key: RuntimeError("private-body") for key in
                    ("config", "policies", "recommendations")})
    record = source.probe_stack(client, STACK, "synthetic")
    assert not record["available"] and "private-body" not in json.dumps(record)
    assert adaptive_traces.build([STACK], {"obs-hub": record}) == ([], {})
    assert source.probe_all(Proxy(), [STACK], {})["obs-hub"]["reason"] == "no_credential"
    assert source.probe_all(Proxy(), [{**STACK, "status": "paused"}], {}) == {}


def test_hydration_keeps_new_input_freshness_and_never_rehydrates_its_own_failed_input():
    import datetime as dt
    now = dt.datetime(2026, 9, 30, tzinfo=dt.timezone.utc)
    data = source.probe_all(Proxy(), [STACK], {"obs-hub": {"token": "synthetic"}})
    scan = {"meta": {"generated_at": now.isoformat(), "tier": "t2"},
            "data": {"adaptive_traces": data}}
    loader = lambda tier, bucket: scan if tier == "t2" else None
    inputs, provenance = hydrate.hydrate("t1", {}, now=now, loader=loader)
    assert inputs["adaptive_traces"] == data
    added = [m for m in hydrate.report_metrics(provenance, "t1")
             if m[1]["input"] == "adaptive_traces"]
    assert {name for name, _, _ in added} == {"gcinsight_input_available", "gcinsight_input_age_seconds"}
    inputs, provenance = hydrate.hydrate("t2", {}, now=now, loader=loader)
    assert "adaptive_traces" not in inputs
    assert not provenance["adaptive_traces"]["available"]


def test_t2_gatherer_uses_inventory_and_sanitizes_store_errors():
    import scan
    with mock.patch.object(scan.credentials, "load_all", return_value={"obs-hub": {"token": "synthetic"}}):
        data, errors = scan.gather_adaptive_traces(Proxy(), None, [STACK])
    assert data["obs-hub"]["policy_count"] == 4 and errors == []
    with mock.patch.object(scan.credentials, "load_all", side_effect=scan.credentials.StoreUnavailable("private")):
        data, errors = scan.gather_adaptive_traces(Proxy(), None, [STACK])
    assert data == {} and "private" not in json.dumps(errors)


def test_inventory_panel_is_on_existing_adaptive_traces_tab():
    from bin import dashboards
    elements = dashboards.BUILDERS["coverage"]("synthetic")[3]
    assert "tbl_at_inventory" in elements
    panel = elements["tbl_at_inventory"]["spec"]
    assert "achieved" in panel["description"].lower()
    query = panel["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
    assert query["filterExpression"] == 'Stack =~ "^(${stack:regex})$"'
