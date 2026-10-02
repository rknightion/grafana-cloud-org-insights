"""Configured reports cross real T2 and publication with only edge fakes."""
import json
from contextlib import ExitStack
from types import SimpleNamespace
from pathlib import Path
from unittest import mock

import pytest
import scan
from collector.coverage import Coverage
from collector.emit import hydrate, s3
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose
from collector.provision import desired_permissions, product_read_pairs, parse_product_reads

STACK = {"slug": "obs-hub", "url": "https://inventory.example.test"}
PRIVATE = "private-report-canary"
BODY = json.loads((Path(__file__).parent / "fixtures/reports.json").read_text())
BODY[0].update({"id": PRIVATE, "name": PRIVATE, "recipients": [PRIVATE], "destinations": [PRIVATE],
                "user": PRIVATE, "schedule": PRIVATE, "dashboards": [{"query": PRIVATE}],
                "options": {"message": PRIVATE}, "timestamp": PRIVATE})
ROW = {"Stack": "obs-hub", "Configured reports": 1}


def client_for(body=BODY, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + "/api/reports"
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


@pytest.mark.parametrize("body,status,measured", [(BODY, 200, True), (BODY, 206, False),
    ([{"id": PRIVATE, "password": PRIVATE}], 200, False), ({"error": PRIVATE}, 403, False)])
def test_selected_full_t2_public_boundary(body, status, measured, capsys, caplog, tmp_path):
    from tests.test_scan import cfg_for
    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "reports"}))
        edges.enter_context(mock.patch.object(scan.credentials, "load_all", return_value={"obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}}))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_inventory", return_value=[STACK]))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail))
        for name in ("service_accounts", "assistant", "insights", "dashboard_inventory", "datasource_query_cost", "adaptive_logs", "adaptive_traces", "public_dashboards", "alert_routing", "slo_inventory", "signal_inventory", "capability_adoption", "loki_config"):
            edges.enter_context(mock.patch.object(scan, "gather_" + name, return_value=({}, [])))
        edges.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value={}))
        edges.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        edges.enter_context(mock.patch.object(hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1)))
        result = scan.run_t2(client_for(body, status), cfg_for())
    if measured:
        assert result["data"]["reports_inventory"] == {"obs-hub": {"available": True, "report_count": 1}}
        assert result["meta"]["sources"]["reports_inventory"]["healthy"]
        assert result["_emit"]["views"]["reports_inventory"] == [ROW]
    else:
        assert "reports_inventory" not in result["data"]
        assert not result["meta"]["sources"]["reports_inventory"]["healthy"]
        assert "reports_inventory" not in result["_emit"]["views"]
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
        s3.write_views(views, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    if measured:
        envelope = json.loads(writes["views/reports_inventory.json"])
        assert envelope["rows"] == [ROW]
        assert envelope["meta"]["inputs"]["reports_inventory"]["source"] == "own"
        assert envelope["meta"]["inputs"]["reports_inventory"]["tier"] == "t2"
    else:
        assert "views/reports_inventory.json" not in writes
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps(scan.label_risk_pillar.diagnostic_scan(result), default=str))
    event = scan.loki.summary_event("t2", result["meta"])
    assert PRIVATE not in diagnostic.read_text() + json.dumps(event) + json.dumps(result) + json.dumps(writes) + caplog.text + capsys.readouterr().out
    from bin import dashboards
    _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "reports_inventory.json" in json.dumps(assembled)


def test_default_off_exact_grants_and_parse():
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), mock.patch.object(scan.credentials, "load_all") as store:
        calls = []
        assert scan.gather_reports_inventory(client_for(calls=calls), SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        store.assert_not_called()
        assert calls == []
    pairs = frozenset({("reports:read", "reports:*")})
    assert product_read_pairs({"reports"}) == pairs
    baseline = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False)}
    selected = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False, product_reads={"reports"})}
    assert selected - baseline == pairs
    assert parse_product_reads("reports") == frozenset({"reports"})
    with pytest.raises(ValueError):
        parse_product_reads("reports-send")
    with pytest.raises(ValueError):
        parse_product_reads("synthetic-monitoring-query,reports")


@pytest.mark.parametrize("body,count", [(BODY, 1), ([], 0), ([{"id": 1}, {"id": "2"}], 2)])
def test_empty_and_fresh_inventory_join(body, count):
    from collector.sources import reports
    record = reports.fetch_reports(client_for(body), STACK, "synthetic")
    assert record == {"available": True, "report_count": count}
    rows = compose.build_all([STACK, {"slug": "added"}], Coverage(tier="t2", total=2), reports_inventory={"obs-hub": record, "departed": record})[1]
    assert rows["reports_inventory"] == [{"Stack": "obs-hub", "Configured reports": count}]
    assert "reports_inventory" not in compose.build_all([], Coverage(tier="t2", total=0), reports_inventory={"departed": record})[1]
    calls = []
    assert set(reports.probe_all(client_for(body, calls=calls), [STACK], {"obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}})) == {"obs-hub"}
    assert len(calls) == 1


@pytest.mark.parametrize("body,status", [({"reports": BODY}, 200), ({"items": [], "partial": False}, 200),
    ({"data": [], "pagination": {}}, 200), ([{}], 200), ([{"id": True}], 200), ([{"id": 0}], 200),
    ([{"id": " "}], 200), ([{"id": []}], 200), ([{"id": PRIVATE, "api_key": PRIVATE}], 200),
    ([{"id": PRIVATE, "options": {"grafanaApiKey": PRIVATE}}], 200), (BODY, 206),
    ({"error": PRIVATE}, 403), ({"error": PRIVATE}, 302)])
def test_unknown_private_absent(body, status, caplog, capsys):
    from collector.sources import reports
    errors = []
    records = reports.probe_all(client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic"}}, on_error=lambda slug, msg: errors.append(msg))
    assert not records["obs-hub"]["available"]
    assert "reports_inventory" not in compose.build_all([STACK], Coverage(tier="t2", total=1), reports_inventory=records)[1]
    assert PRIVATE not in json.dumps([records, errors]) + caplog.text + capsys.readouterr().out


def test_bounds_and_errors():
    from collector.sources import reports, resource_schema
    with mock.patch.object(reports, "MAX_REPORTS", 0):
        assert not reports.fetch_reports(client_for(), STACK, "synthetic")["available"]
    assert not reports.fetch_reports(client_for([{"id": 1, "name": "x" * (2 * 1024 * 1024)}]), STACK, "synthetic")["available"]
    with mock.patch.object(resource_schema, "MAX_DEPTH", 1):
        assert not reports.fetch_reports(client_for(), STACK, "synthetic")["available"]
    client = mock.Mock()
    client.get.side_effect = RuntimeError(PRIVATE)
    assert reports.fetch_reports(client, STACK, "synthetic") == {"available": False, "reason": "transport_error"}
    assert reports.fetch_reports(client, STACK, "") == {"available": False, "reason": "no_credential"}
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "reports"}), mock.patch.object(scan.credentials, "load_all", side_effect=scan.credentials.StoreUnavailable(PRIVATE)):
        assert scan.gather_reports_inventory(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, ["reports_inventory: credential_store_unavailable"])


@pytest.mark.parametrize("url", ["http://host.test", "https://u:p@host.test", "https://host.test/?x=y", "https://host.test/#x", "https://host.test/%61pi"])
def test_unsafe_origin_zero_calls(url):
    from collector.sources import reports
    calls = []
    assert not reports.fetch_reports(client_for(calls=calls), {**STACK, "url": url}, "synthetic")["available"]
    assert calls == []


def test_optional_missing_table_and_retained_view():
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def missing(name):
        if name == "reports_inventory":
            raise FileNotFoundError(name)
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=missing):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "reports_inventory.json" not in json.dumps(assembled)
    assert "ml_jobs.json" in json.dumps(assembled)
    assert "_age_reports_inventory" in assembled["spec"]["elements"]
    def retained(name):
        return {"meta": {"generated_at": "2020-01-01T00:00:00Z"}, "rows": [ROW]} if name == "reports_inventory" else real_read(name)
    with mock.patch.object(build, "read_view", side_effect=retained):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "reports_inventory.json" in json.dumps(assembled)
    assert "time()" in json.dumps(assembled["spec"]["elements"]["_age_reports_inventory"])
    _, provenance = hydrate.hydrate("t2", {}, loader=lambda tier, bucket: None)
    views, withheld = hydrate.filter_views({"reports_inventory": [ROW]}, provenance)
    assert "reports_inventory" not in views
    assert "reports_inventory" in withheld


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("transport"), json.JSONDecodeError("invalid", "", 0)])
def test_optional_access_parse_errors_explicit(error):
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def read(name):
        if name == "reports_inventory":
            raise error
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=read), pytest.raises(type(error)):
        dashboards.assemble("usage", "infinity-uid")
