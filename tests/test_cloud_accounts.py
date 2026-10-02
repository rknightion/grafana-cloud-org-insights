"""AWS count selection crosses the real T2 boundary, never live systems."""
import json
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector.httpclient import ReadOnlyClient, Response

STACK = {"slug": "obs-hub", "id": 123, "url": "https://inventory.example.test"}
PATH = "/api/plugin-proxy/grafana-csp-app/he-api/api/v2/stacks/123/aws/accounts"
PRIVATE = "private-cloud-canary"
BODY = json.loads((Path(__file__).parent / "fixtures/cloud_accounts.json").read_text())
BODY["data"][0].update({"id": PRIVATE, "name": PRIVATE, "role_arn": PRIVATE,
                        "regions": [PRIVATE], "config": {"detail": PRIVATE}})
ROW = {"Stack": "obs-hub", "Provider": "aws", "Configured accounts": 1}


def client_for(body, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + PATH
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


@pytest.mark.parametrize("body,status,measured", [(BODY, 200, True),
    ({"data": [{"id": PRIVATE, "password": PRIVATE}]}, 200, False),
    ({"error": PRIVATE}, 403, False)])
def test_selected_full_t2_public_boundary(body, status, measured, capsys, caplog, tmp_path):
    from tests.test_scan import cfg_for
    from collector.emit import hydrate, s3
    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "cloud-accounts"}))
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
        assert result["data"]["cloud_accounts"] == {"obs-hub": {"available": True, "account_count": 1}}
        assert result["meta"]["sources"]["cloud_accounts"]["healthy"]
        assert result["_emit"]["views"]["cloud_accounts"] == [ROW]
    else:
        assert "cloud_accounts" not in result["data"]
        assert not result["meta"]["sources"]["cloud_accounts"]["healthy"]
        assert "cloud_accounts" not in result["_emit"]["views"]
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
        s3.write_views(views, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    if measured:
        envelope = json.loads(writes["views/cloud_accounts.json"])
        assert envelope["rows"] == [ROW]
        assert envelope["meta"]["inputs"]["cloud_accounts"]["source"] == "own"
        assert envelope["meta"]["inputs"]["cloud_accounts"]["tier"] == "t2"
    else:
        assert "views/cloud_accounts.json" not in writes
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps(scan.label_risk_pillar.diagnostic_scan(result), default=str))
    event = scan.loki.summary_event("t2", result["meta"])
    assert PRIVATE not in diagnostic.read_text() + json.dumps(event) + json.dumps(result) + json.dumps(writes) + caplog.text + capsys.readouterr().out
    from bin import dashboards
    _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "cloud_accounts.json" in json.dumps(assembled)


def test_default_off_and_exact_grants():
    from collector.provision import desired_permissions, product_read_pairs
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), mock.patch.object(scan.credentials, "load_all") as store:
        calls = []
        assert scan.gather_cloud_accounts(client_for([], calls=calls), SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        store.assert_not_called()
        assert calls == []
    pairs = frozenset({("grafana-csp-app:read", ""), ("plugins.app:access", "plugins:id:grafana-csp-app")})
    assert product_read_pairs({"cloud-accounts"}) == pairs
    baseline = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False)}
    selected = {(p["action"], p.get("scope", "")) for p in desired_permissions(write_stack=False, product_reads={"cloud-accounts"})}
    assert selected - baseline == pairs
    assert not any("write" in action or action == "datasources:query" for action, _ in pairs)


@pytest.mark.parametrize("body,count", [(BODY, 1), ({"data": []}, 0)])
def test_empty_and_inventory_left_join(body, count):
    from collector.sources import cloud_accounts as source
    from collector.pillars import compose
    from collector.coverage import Coverage
    record = source.fetch_cloud_accounts(client_for(body), STACK, "synthetic")
    assert record == {"available": True, "account_count": count}
    views = compose.build_all([STACK, {"slug": "added"}], Coverage(tier="t2", total=2), cloud_accounts={"obs-hub": record, "departed": record})[1]
    assert views["cloud_accounts"] == [{"Stack": "obs-hub", "Provider": "aws", "Configured accounts": count}]
    assert "cloud_accounts" not in compose.build_all([], Coverage(tier="t2", total=0), cloud_accounts={"departed": record})[1]
    calls = []
    records = source.probe_all(client_for(body, calls=calls), [STACK, {**STACK, "slug": "added"}, {**STACK, "slug": "paused", "status": "paused"}],
                               {"obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}})
    assert set(records) == {"obs-hub", "added"}
    assert records["added"] == {"available": False, "reason": "no_credential"}
    assert calls == [STACK["url"] + PATH]


@pytest.mark.parametrize("body,status", [
    ({"data": [], "pagination": {}}, 200), ({"data": [], "partial": False}, 200),
    ({"data": [], "next": PRIVATE}, 200), ({"data": {}}, 200), ([], 200),
    ({"data": [{"id": ""}]}, 200), ({"data": [{"id": " "}]}, 200),
    ({"data": [{"id": 123}]}, 200), ({"data": [None]}, 200),
    ({"data": [{"id": PRIVATE, "grafanaApiKey": PRIVATE}]}, 200),
    ({"data": [{"id": PRIVATE, "config": {"password": PRIVATE}}]}, 200),
    ({"data": [{"id": PRIVATE, "api_key": PRIVATE}]}, 200),
    ({"error": PRIVATE}, 401), ({"error": PRIVATE}, 403),
    ({"error": PRIVATE}, 500), ({"error": PRIVATE}, 302),
    (BODY, 206)])
def test_failure_absent_private(body, status, capsys, caplog):
    from collector.sources import cloud_accounts as source
    from collector.pillars import compose
    from collector.coverage import Coverage
    errors = []
    records = source.probe_all(client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic"}}, on_error=lambda slug, msg: errors.append(msg))
    assert records["obs-hub"]["available"] is False
    assert "cloud_accounts" not in compose.build_all([STACK], Coverage(tier="t2", total=1), cloud_accounts=records)[1]
    assert PRIVATE not in json.dumps([records, errors]) + caplog.text + capsys.readouterr().out


def test_bounds_transport_and_store():
    from collector.sources import cloud_accounts as source, resource_schema
    with mock.patch.object(source, "MAX_ACCOUNTS", 0):
        assert not source.fetch_cloud_accounts(client_for(BODY), STACK, "synthetic")["available"]
    huge = {"data": [{"id": "synthetic", "name": "x" * (2 * 1024 * 1024)}]}
    assert not source.fetch_cloud_accounts(client_for(huge), STACK, "synthetic")["available"]
    with mock.patch.object(resource_schema, "MAX_DEPTH", 1):
        assert source.fetch_cloud_accounts(client_for(BODY), STACK, "synthetic") == {"available": False, "reason": "unsafe_schema"}
    with mock.patch.object(resource_schema, "MAX_NODES", 1):
        assert source.fetch_cloud_accounts(client_for(BODY), STACK, "synthetic") == {"available": False, "reason": "unsafe_schema"}
    client = mock.Mock()
    client.get.side_effect = RuntimeError(PRIVATE)
    assert source.fetch_cloud_accounts(client, STACK, "synthetic") == {"available": False, "reason": "transport_error"}
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "cloud-accounts"}), mock.patch.object(scan.credentials, "load_all", side_effect=scan.credentials.StoreUnavailable(PRIVATE)):
        assert scan.gather_cloud_accounts(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, ["cloud_accounts: credential_store_unavailable"])


@pytest.mark.parametrize("url", ["http://host.test", "https://u:p@host.test", "https://host.test/?x=y", "https://host.test/#x", "https://host.test/%61pi"])
def test_origin_rejected(url):
    from collector.sources import cloud_accounts as source
    client = mock.Mock()
    assert source.fetch_cloud_accounts(client, {**STACK, "url": url}, "synthetic") == {"available": False, "reason": "invalid_url"}
    client.get.assert_not_called()


@pytest.mark.parametrize("stack_id", [None, True, 0, -1, 1.0, "123/aws", "123?x=y", "01", "1" * 21])
def test_invalid_stack_id_rejected_before_http(stack_id):
    from collector.sources import cloud_accounts as source
    client = mock.Mock()
    assert source.fetch_cloud_accounts(client, {**STACK, "id": stack_id}, "synthetic") == {"available": False, "reason": "invalid_stack_id"}
    client.get.assert_not_called()


@pytest.mark.parametrize("location", ["https://attacker.example.test/capture", STACK["url"] + "/off-route"])
def test_real_redirect_never_forwards_reader(monkeypatch, location):
    from collector.sources import cloud_accounts as source
    from tests.test_slo_inventory import wire, WireBody
    calls = wire(monkeypatch, lambda req: (302, {"Location": location}, WireBody(b"")))
    assert source.fetch_cloud_accounts(ReadOnlyClient(max_attempts=1), STACK, "synthetic-token") == {"available": False, "reason": "unreadable"}
    assert len(calls) == 1
    assert calls[0].full_url == STACK["url"] + PATH


def test_fresh_inventory_id_and_account_url_are_not_confused():
    from collector.sources import cloud_accounts as source
    client = mock.Mock()
    client.get.return_value = Response(200, json.dumps({"data": [{"id": "synthetic", "url": "https://untrusted.example"}]}).encode(), "")
    assert source.fetch_cloud_accounts(client, {**STACK, "id": "456"}, "synthetic") == {"available": True, "account_count": 1}
    client.get.assert_called_once_with(STACK["url"] + PATH.replace("/123/", "/456/"), bearer="synthetic", guarded=True)


def test_optional_missing_only_and_retained_view():
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def missing(name):
        if name == "cloud_accounts":
            raise FileNotFoundError(name)
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=missing):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "cloud_accounts.json" not in json.dumps(assembled)
    assert "ml_jobs.json" in json.dumps(assembled)
    assert "_age_cloud_accounts" in assembled["spec"]["elements"]
    def retained(name):
        return {"meta": {"generated_at": "2020-01-01T00:00:00Z"}, "rows": [ROW]} if name == "cloud_accounts" else real_read(name)
    with mock.patch.object(build, "read_view", side_effect=retained):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "cloud_accounts.json" in json.dumps(assembled)
    assert "time()" in json.dumps(assembled["spec"]["elements"]["_age_cloud_accounts"])


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("transport"), json.JSONDecodeError("invalid", "", 0)])
def test_optional_access_schema_failures_explicit(error):
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def read(name):
        if name == "cloud_accounts":
            raise error
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=read), pytest.raises(type(error)):
        dashboards.assemble("usage", "infinity-uid")
