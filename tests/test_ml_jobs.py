"""ML named-route count boundary; keys and job details stay transient."""
import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector.coverage import Coverage
from collector.emit import hydrate, s3
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose
from collector.provision import desired_permissions, product_read_pairs

STACK = {"slug": "obs-hub", "url": "https://inventory.example.test"}
PATH = "/api/plugins/grafana-ml-app/resources/manage/api/v1/jobs"
PRIVATE = "private-ml-canary"
BODY = json.loads((Path(__file__).parent / "fixtures/ml_jobs.json").read_text())
BODY["data"][0].update({"id": PRIVATE, "grafanaApiKey": PRIVATE,
        "name": PRIVATE, "queryParams": {"expr": PRIVATE}, "labels": {"value": PRIVATE},
        "datasourceUid": PRIVATE, "config": {"algorithm": PRIVATE}, "user": PRIVATE})
ROW = {"Stack": "obs-hub", "Configured forecast jobs": 1}


def client_for(body, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + PATH
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


@pytest.mark.parametrize("body,status,measured", [(BODY, 200, True),
    ({"status": "success", "data": [{"id": PRIVATE, "password": PRIVATE}]}, 200, False),
    ({"error": PRIVATE}, 403, False)])
def test_selected_full_t2_public_boundary(body, status, measured, capsys, caplog, tmp_path):
    from tests.test_scan import cfg_for
    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "ml-jobs"}))
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
        assert result["data"]["ml_jobs"] == {"obs-hub": {"available": True, "job_count": 1}}
        assert result["meta"]["sources"]["ml_jobs"]["healthy"]
        assert result["_emit"]["views"]["ml_jobs"] == [ROW]
    else:
        assert "ml_jobs" not in result["data"]
        assert not result["meta"]["sources"]["ml_jobs"]["healthy"]
        assert "ml_jobs" not in result["_emit"]["views"]
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
        s3.write_views(views, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    if measured:
        envelope = json.loads(writes["views/ml_jobs.json"])
        assert envelope["rows"] == [ROW]
        assert envelope["meta"]["inputs"]["ml_jobs"]["source"] == "own"
        assert envelope["meta"]["inputs"]["ml_jobs"]["tier"] == "t2"
    else:
        assert "views/ml_jobs.json" not in writes
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps(scan.label_risk_pillar.diagnostic_scan(result), default=str))
    event = scan.loki.summary_event("t2", result["meta"])
    assert PRIVATE not in diagnostic.read_text() + json.dumps(event) + json.dumps(result) + json.dumps(writes) + caplog.text + capsys.readouterr().out
    from bin import dashboards
    _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "ml_jobs.json" in json.dumps(assembled)


def test_default_off_and_exact_grants():
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), mock.patch.object(scan.credentials, "load_all") as store:
        calls = []
        assert scan.gather_ml_jobs(client_for([], calls=calls), SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        store.assert_not_called()
        assert calls == []
    pairs = frozenset({("grafana-ml-app.forecasting:read", ""), ("plugins.app:access", "plugins:id:grafana-ml-app")})
    assert product_read_pairs({"ml-jobs"}) == pairs
    baseline = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False)}
    selected = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False, product_reads={"ml-jobs"})}
    assert selected - baseline == pairs


@pytest.mark.parametrize("body,count", [(BODY, 1), ({"status": "success", "data": []}, 0)])
def test_empty_and_inventory_left_join(body, count):
    from collector.sources import ml_jobs as source
    record = source.fetch_ml_jobs(client_for(body), STACK, "synthetic")
    assert record == {"available": True, "job_count": count}
    views = compose.build_all([STACK, {"slug": "added"}], Coverage(tier="t2", total=2), ml_jobs={"obs-hub": record, "departed": record})[1]
    assert views["ml_jobs"] == [{"Stack": "obs-hub", "Configured forecast jobs": count}]
    assert "ml_jobs" not in compose.build_all([], Coverage(tier="t2", total=0), ml_jobs={"departed": record})[1]


@pytest.mark.parametrize("body,status", [
    ({"status": "error", "data": [], "message": PRIVATE}, 200),
    ({"status": "success", "data": [], "pagination": {}}, 200),
    ({"status": "success", "data": [], "partial": False}, 200),
    ({"status": "success", "data": {}}, 200),
    ({"status": "success", "data": [{"id": ""}]}, 200),
    ({"status": "success", "data": [{"id": PRIVATE, "password": PRIVATE}]}, 200),
    ({"status": "success", "data": [{"id": PRIVATE, "config": {"grafanaApiKey": PRIVATE}}]}, 200),
    ({"status": "success", "data": [{"id": PRIVATE, "api_key": PRIVATE}]}, 200),
    ({"error": PRIVATE}, 403), ({"error": PRIVATE}, 500), ({"error": PRIVATE}, 302)])
def test_failure_absent_private(body, status, capsys, caplog):
    from collector.sources import ml_jobs as source
    errors = []
    records = source.probe_all(client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic"}}, on_error=lambda slug, msg: errors.append(msg))
    assert records["obs-hub"]["available"] is False
    assert "ml_jobs" not in compose.build_all([STACK], Coverage(tier="t2", total=1), ml_jobs=records)[1]
    assert PRIVATE not in json.dumps([records, errors]) + caplog.text + capsys.readouterr().out


def test_bounds_transport_and_store():
    from collector.sources import ml_jobs as source
    with mock.patch.object(source, "MAX_JOBS", 0):
        assert not source.fetch_ml_jobs(client_for(BODY), STACK, "synthetic")["available"]
    huge = {"status": "success", "data": [{"id": "synthetic", "name": "x" * (2 * 1024 * 1024)}]}
    assert not source.fetch_ml_jobs(client_for(huge), STACK, "synthetic")["available"]
    from collector.sources import resource_schema
    with mock.patch.object(resource_schema, "MAX_DEPTH", 1):
        assert not source.fetch_ml_jobs(client_for(BODY), STACK, "synthetic")["available"]
    client = mock.Mock()
    client.get.side_effect = RuntimeError(PRIVATE)
    assert source.fetch_ml_jobs(client, STACK, "synthetic") == {"available": False, "reason": "transport_error"}
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "ml-jobs"}), mock.patch.object(scan.credentials, "load_all", side_effect=scan.credentials.StoreUnavailable(PRIVATE)):
        assert scan.gather_ml_jobs(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, ["ml_jobs: credential_store_unavailable"])


@pytest.mark.parametrize("url", ["http://host.test", "https://u:p@host.test", "https://host.test/?x=y", "https://host.test/#x", "https://host.test/%61pi"])
def test_origin_rejected(url):
    from collector.sources import ml_jobs as source
    calls = []
    assert not source.fetch_ml_jobs(client_for(BODY, calls=calls), {**STACK, "url": url}, "synthetic")["available"]
    assert calls == []


def test_optional_missing_only_and_retained_view():
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def missing(name):
        if name == "ml_jobs":
            raise FileNotFoundError(name)
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=missing):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "ml_jobs.json" not in json.dumps(assembled)
    assert "faro_apps.json" in json.dumps(assembled)
    assert "_age_ml_jobs" in assembled["spec"]["elements"]
    def retained(name):
        return {"meta": {"generated_at": "2020-01-01T00:00:00Z"}, "rows": [ROW]} if name == "ml_jobs" else real_read(name)
    with mock.patch.object(build, "read_view", side_effect=retained):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "ml_jobs.json" in json.dumps(assembled)
    assert "time()" in json.dumps(assembled["spec"]["elements"]["_age_ml_jobs"])


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("transport"), json.JSONDecodeError("invalid", "", 0)])
def test_optional_access_schema_failures_explicit(error):
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def read(name):
        if name == "ml_jobs":
            raise error
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=read), pytest.raises(type(error)):
        dashboards.assemble("usage", "infinity-uid")
