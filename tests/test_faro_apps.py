"""Faro count-only public boundary; all upstream details remain transient."""
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
PATH = "/api/plugin-proxy/grafana-kowalski-app/api-proxy/api/v1/app"
PRIVATE = "private-faro-canary"
BODY = json.loads((Path(__file__).parent / "fixtures/faro_apps.json").read_text())
BODY[0].update({"name": PRIVATE, "appKey": PRIVATE, "collectEndpointURL": PRIVATE,
                "otlpEndpointURL": PRIVATE, "corsOrigins": [PRIVATE], "settings": {"value": PRIVATE},
                "rate": PRIVATE, "createdAt": PRIVATE})
COUNTS = {"web": 1, "mobile": 1, "unknown": 0}
ROW = {"Stack": "obs-hub", "Configured Faro apps": 2, "Web apps": 1, "Mobile apps": 1, "Unknown type apps": 0}


def client_for(body, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + PATH
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


@pytest.mark.parametrize("status,measured", [(200, True), (206, False)])
def test_selected_full_t2_public_boundary(status, measured, capsys, caplog):
    from tests.test_scan import cfg_for
    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "faro-apps"}))
        edges.enter_context(mock.patch.object(scan.credentials, "load_all", return_value={"obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}}))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_inventory", return_value=[STACK]))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail))
        for name in ("service_accounts", "assistant", "insights", "dashboard_inventory", "datasource_query_cost", "adaptive_logs", "adaptive_traces", "public_dashboards", "alert_routing", "slo_inventory", "signal_inventory", "capability_adoption", "loki_config"):
            edges.enter_context(mock.patch.object(scan, "gather_" + name, return_value=({}, [])))
        edges.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value={}))
        edges.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        edges.enter_context(mock.patch.object(hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1)))
        result = scan.run_t2(client_for(BODY, status), cfg_for())
    if measured:
        assert result["data"]["faro_apps"] == {"obs-hub": {"available": True, "app_count": 2, "app_types": COUNTS}}
        assert result["meta"]["sources"]["faro_apps"]["healthy"]
        assert result["_emit"]["views"]["faro_apps"] == [ROW]
    else:
        assert "faro_apps" not in result["data"]
        assert not result["meta"]["sources"]["faro_apps"]["healthy"]
        assert "faro_apps" not in result["_emit"]["views"]
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
        s3.write_views(views, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    if measured:
        envelope = json.loads(writes["views/faro_apps.json"])
        assert envelope["rows"] == [ROW]
        assert envelope["meta"]["inputs"]["faro_apps"]["source"] == "own"
        assert envelope["meta"]["inputs"]["faro_apps"]["tier"] == "t2"
    else:
        assert "views/faro_apps.json" not in writes
    assert PRIVATE not in json.dumps(result) + json.dumps(writes) + caplog.text + capsys.readouterr().out
    from bin import dashboards
    _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "faro_apps.json" in json.dumps(assembled)


def test_default_off_and_exact_grants():
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), mock.patch.object(scan.credentials, "load_all") as store:
        calls = []
        assert scan.gather_faro_apps(client_for([], calls=calls), SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        store.assert_not_called()
        assert calls == []
    pairs = frozenset({("grafana-kowalski-app.apps:read", ""), ("plugins.app:access", "plugins:id:grafana-kowalski-app")})
    assert product_read_pairs({"faro-apps"}) == pairs
    baseline = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False)}
    selected = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False, product_reads={"faro-apps"})}
    assert selected - baseline == pairs


@pytest.mark.parametrize("body,types", [([], {"web": 0, "mobile": 0, "unknown": 0}), (BODY, COUNTS), ([{"appType": PRIVATE}, {}], {"web": 0, "mobile": 0, "unknown": 2})])
def test_empty_unknown_and_inventory_left_join(body, types):
    from collector.sources import faro_apps as source
    record = source.fetch_faro_apps(client_for(body), STACK, "synthetic")
    assert record == {"available": True, "app_count": len(body), "app_types": types}
    records = {"obs-hub": record, "departed": record}
    views = compose.build_all([STACK, {"slug": "added"}], Coverage(tier="t2", total=2), faro_apps=records)[1]
    assert len(views["faro_apps"]) == 1
    assert views["faro_apps"][0]["Stack"] == "obs-hub"
    assert "faro_apps" not in compose.build_all([], Coverage(tier="t2", total=0), faro_apps=records)[1]


@pytest.mark.parametrize("body,status", [(BODY, 206), ([], 206), ({"apps": BODY}, 200), ([{}, PRIVATE], 200), ([{"appType": []}], 200), ({"error": PRIVATE}, 403), ({"error": PRIVATE}, 500)])
def test_failure_absent_private(body, status, capsys, caplog):
    from collector.sources import faro_apps as source
    errors = []
    records = source.probe_all(client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic"}}, on_error=lambda slug, msg: errors.append(msg))
    assert records["obs-hub"]["available"] is False
    if status == 206:
        assert records["obs-hub"] == {"available": False, "reason": "unreadable"}
        assert errors == ["faro_apps: unreadable"]
    assert "faro_apps" not in compose.build_all([STACK], Coverage(tier="t2", total=1), faro_apps=records)[1]
    assert PRIVATE not in json.dumps([records, errors]) + caplog.text + capsys.readouterr().out


def test_oversize_and_transport_private():
    from collector.sources import faro_apps as source
    with mock.patch.object(source, "MAX_APPS", 1):
        assert source.fetch_faro_apps(client_for(BODY), STACK, "synthetic")["available"] is False
    client = mock.Mock()
    client.get.side_effect = RuntimeError(PRIVATE)
    assert source.fetch_faro_apps(client, STACK, "synthetic") == {"available": False, "reason": "transport_error"}


@pytest.mark.parametrize("url", ["http://host.test", "https://u:p@host.test", "https://host.test/?x=y", "https://host.test/#x", "https://host.test/%61pi"])
def test_origin_rejected(url):
    from collector.sources import faro_apps as source
    calls = []
    assert not source.fetch_faro_apps(client_for([], calls=calls), {**STACK, "url": url}, "synthetic")["available"]
    assert calls == []


def test_optional_missing_only_and_retained_view():
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def missing(name):
        if name == "faro_apps":
            raise FileNotFoundError(name)
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=missing):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "faro_apps.json" not in json.dumps(assembled)
    assert "irm_integrations.json" in json.dumps(assembled)
    assert "_age_faro_apps" in assembled["spec"]["elements"]
    def retained(name):
        return {"meta": {"generated_at": "2020-01-01T00:00:00Z"}, "rows": [ROW]} if name == "faro_apps" else real_read(name)
    with mock.patch.object(build, "read_view", side_effect=retained):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "faro_apps.json" in json.dumps(assembled)
    assert "time()" in json.dumps(assembled["spec"]["elements"]["_age_faro_apps"])


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("transport"), json.JSONDecodeError("invalid", "", 0)])
def test_optional_access_schema_failures_explicit(error):
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def read(name):
        if name == "faro_apps":
            raise error
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=read), pytest.raises(type(error)):
        dashboards.assemble("usage", "infinity-uid")
