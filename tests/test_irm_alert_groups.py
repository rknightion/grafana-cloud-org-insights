"""Default-off minimized IRM alert-group stats from the exact witnessed GET."""
import json
from contextlib import ExitStack
from types import SimpleNamespace
from unittest import mock

import pytest

from collector.coverage import Coverage
from collector.emit import hydrate, s3
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose
from collector.sources import irm_alert_groups as source

STACK = {"slug": "obs-hub", "url": "https://inventory.example.test"}
PATH = "/api/plugins/grafana-irm-app/resources/alertgroups/stats/"
SENTINEL = "private-alert-content-sentinel"


def client_for(body, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append((request.method, request.full_url))
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


def test_count_and_bounded_semantics_only():
    result = source.fetch_irm_alert_groups(client_for({"count": "14"}), STACK, "synthetic-reader")
    assert result == {
        "available": True,
        "alert_group_count": 14,
        "relation": "exact",
        "population": "api_default_window",
    }
    lower_bound = source.fetch_irm_alert_groups(
        client_for({"count": "100000+"}), STACK, "synthetic-reader",
    )
    assert lower_bound == {
        "available": True,
        "alert_group_count": 100000,
        "relation": "at_least",
        "population": "api_default_window",
    }
    zero = source.fetch_irm_alert_groups(client_for({"count": "0"}), STACK, "synthetic-reader")
    assert zero["alert_group_count"] == 0 and zero["relation"] == "exact"


def test_exact_route_and_projection_rejects_content():
    calls = []
    client = client_for({"count": "14", "title": SENTINEL}, calls=calls)
    result = source.fetch_irm_alert_groups(client, STACK, "synthetic-reader")
    assert result == {"available": False, "reason": "invalid_response"}
    assert calls == [("GET", STACK["url"] + PATH)]
    assert SENTINEL not in json.dumps(result)


def test_bad_counts_are_unavailable_not_zero():
    # These classes pin the actual parsing risks: canonical form, trailing-plus relation,
    # strict string shape, and bounded integer size.
    for value in ("", "00", "01", "+1", " 1", "1 ", "1.0", "1e2", "-1", "12++",
                  "9999999999999999999", True, None, 1):
        result = source.fetch_irm_alert_groups(client_for({"count": value}), STACK, "synthetic-reader")
        assert result == {"available": False, "reason": "invalid_response"}


@pytest.mark.parametrize("body,status", [
    ({"count": "14"}, 206), ({"count": "14", "private": SENTINEL}, 200),
    ([{"count": "14"}], 200), ({"error": SENTINEL}, 403),
])
def test_partial_unexpected_or_error_payloads_are_unavailable_and_private(body, status, caplog, capsys):
    errors = []
    result = source.probe_all(
        client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic-reader"}},
        on_error=lambda slug, message: errors.append(message),
    )
    assert result["obs-hub"]["available"] is False
    assert SENTINEL not in json.dumps([result, errors]) + caplog.text + capsys.readouterr().out
    if status == 206:
        assert result["obs-hub"]["reason"] == "unreadable"


def test_transport_exception_content_is_not_retained():
    def fail(request, timeout):
        raise RuntimeError(SENTINEL)
    client = ReadOnlyClient(transport=fail, max_attempts=1)
    errors = []
    result = source.probe_all(
        client, [STACK], {"obs-hub": {"token": "synthetic-reader"}},
        on_error=lambda slug, message: errors.append(message),
    )
    assert result["obs-hub"] == {"available": False, "reason": "transport_error"}
    assert SENTINEL not in json.dumps([result, errors])


def test_inventory_join_addition_removal_and_paused_skip():
    calls = []
    stacks = [STACK, {"slug": "new-stack", "url": "https://new.example.test"},
              {"slug": "paused", "status": "paused", "url": "https://paused.example.test"}]
    client = client_for({"count": "2+"}, calls=calls)
    rows = source.probe_all(
        client, stacks,
        {"obs-hub": {"token": "reader"}, "departed": {"token": "reader"}},
        concurrency=1,
    )
    assert set(rows) == {"obs-hub", "new-stack"}
    assert rows["obs-hub"]["relation"] == "at_least"
    assert rows["new-stack"] == {"available": False, "reason": "no_credential"}
    assert calls == [("GET", STACK["url"] + PATH)]


def test_default_off_does_not_read_credentials_or_call_route(monkeypatch):
    import scan
    calls = []
    monkeypatch.delenv("GCINSIGHT_READER_PRODUCT_READS", raising=False)
    with mock.patch.object(scan.credentials, "load_all") as load:
        assert scan.gather_irm_alert_groups(
            client_for({}, calls=calls), SimpleNamespace(concurrency=1), [STACK],
        ) == ({}, [])
        load.assert_not_called()
    assert calls == []


def test_t2_gather_compose_view_and_usage_dashboard_boundary(monkeypatch):
    import scan
    from collector.dashboards import build as dashboard_build
    from bin import dashboards
    from tests.test_scan import cfg_for

    monkeypatch.setenv("GCINSIGHT_READER_PRODUCT_READS", "irm-alert-groups")

    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}

    with ExitStack() as edges:
        edges.enter_context(mock.patch.object(scan.credentials, "load_all", return_value={
            "obs-hub": {"token": "synthetic-reader"}, "departed": {"token": "synthetic-reader"},
        }))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_inventory", return_value=[STACK]))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail))
        for name in ("service_accounts", "assistant", "insights", "dashboard_inventory",
                     "datasource_query_cost", "adaptive_logs", "adaptive_traces", "public_dashboards",
                     "alert_routing", "slo_inventory", "synthetic_inventory", "signal_inventory",
                     "capability_adoption", "loki_config"):
            edges.enter_context(mock.patch.object(scan, "gather_" + name, return_value=({}, [])))
        edges.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value={}))
        edges.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        edges.enter_context(mock.patch.object(
            scan.hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1),
        ))
        result = scan.run_t2(client_for({"count": "14"}), cfg_for())

    data = result["data"]["irm_alert_groups"]
    errors = result["meta"]["error_samples"]
    assert data == {"obs-hub": {
        "available": True, "alert_group_count": 14, "relation": "exact",
        "population": "api_default_window",
    }}
    assert errors == []
    views = result["_emit"]["views"]
    metrics = result["_emit"]["metrics"]
    assert not any("irm_alert_groups" in name for name, _, _ in metrics)
    expected = [{"Stack": "obs-hub", "IRM alert groups": 14,
                 "Relation": "exact", "Population": "api_default_window"}]
    assert views["irm_alert_groups"] == expected
    retained, withheld = hydrate.filter_views(
        views, hydrate.Provenance(result["meta"]["inputs"]),
    )
    assert retained["irm_alert_groups"] == expected
    assert "irm_alert_groups" not in withheld

    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        s3.write_views(
            retained, result["meta"], view_coverage=result["_emit"]["view_coverage"],
        )
    persisted = json.loads(writes["views/irm_alert_groups.json"])
    assert persisted["rows"] == expected
    assert persisted["meta"]["inputs"]["irm_alert_groups"]["source"] == "own"
    encoded = json.dumps({"data": data, "errors": errors, "view": persisted})
    assert SENTINEL not in encoded
    assert "status=0" not in encoded

    real_read = dashboard_build.read_view
    def read_view(name):
        if name == "irm_alert_groups":
            return persisted
        return real_read(name)
    with mock.patch.object(dashboard_build, "read_view", side_effect=read_view):
        uid, assembled = dashboards.assemble("usage", "infinity-uid")
    assert uid == "gcinsight-usage"
    dashboard = json.dumps(assembled)
    assert "views/irm_alert_groups.json" in dashboard
    assert "api_default_window" in dashboard
    assert "lower bound" in dashboard

    def missing_view(name):
        if name == "irm_alert_groups":
            raise FileNotFoundError("views/irm_alert_groups.json missing")
        return real_read(name)
    with mock.patch.object(dashboard_build, "read_view", side_effect=missing_view):
        _, without_optional = dashboards.assemble("usage", "infinity-uid")
    assert "irm_alert_groups.json" not in json.dumps(without_optional)

    def forbidden_view(name):
        if name == "irm_alert_groups":
            raise PermissionError("denied")
        return real_read(name)
    with (
        mock.patch.object(dashboard_build, "read_view", side_effect=forbidden_view),
        pytest.raises(PermissionError),
    ):
        dashboards.assemble("usage", "infinity-uid")


def test_unavailable_t2_result_never_composes_a_structural_zero():
    from collector.pillars import irm_alert_groups as pillar
    unavailable = {"obs-hub": {"available": False, "reason": "unreadable"}}
    assert pillar.build([STACK], unavailable) == ([], {})
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        s3.write_views({}, {"generated_at": "2026-10-03T12:00:00Z"})
    assert "views/irm_alert_groups.json" not in writes
    assert pillar.build([STACK], {"obs-hub": {
        "available": True, "alert_group_count": 0, "relation": "exact",
        "population": "api_default_window",
    }})[1] == {"irm_alert_groups": [{
        "Stack": "obs-hub", "IRM alert groups": 0,
        "Relation": "exact", "Population": "api_default_window",
    }]}
