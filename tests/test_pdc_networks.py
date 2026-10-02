"""PDC counts cross selected T2 with process-edge fakes, never live systems."""
import json
from contextlib import ExitStack
from types import SimpleNamespace
from pathlib import Path
from copy import deepcopy
from unittest import mock
from urllib.parse import parse_qs, urlsplit

import pytest
import scan
from collector.httpclient import ReadOnlyClient, Response

STACK = {"slug": "obs-hub", "id": 123, "url": "https://inventory.example.test", "regionSlug": "new-region"}
PATH = "/api/plugin-proxy/grafana-pdc-app/grafanacom-api/v1/accesspolicies"
PRIVATE = "private-pdc-canary"
POLICY = {"id": PRIVATE, "name": PRIVATE, "labels": {"detail": PRIVATE}, "address": PRIVATE,
          "realms": [{"type": "stack", "identifier": "123"}], "scopes": ["set:pdc-signing"]}
BODY = json.loads((Path(__file__).parent / "fixtures/pdc_networks.json").read_text())
BODY["items"][0] = POLICY
ROW = {"Stack": "obs-hub", "Configured private networks": 1}


def client_for(body=BODY, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        parsed = urlsplit(request.full_url)
        assert request.method == "GET"
        assert parsed.scheme + "://" + parsed.netloc == STACK["url"]
        assert parsed.path == PATH
        query = parse_qs(parsed.query)
        assert query["realmType"] == ["stack"]
        assert query["realmIdentifier"] == ["123"]
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


@pytest.mark.parametrize("body,status,measured", [(BODY, 200, True), ({"items": []}, 200, False), ({"error": PRIVATE}, 403, False)])
def test_selected_full_t2_public_boundary(body, status, measured, capsys, caplog, tmp_path):
    from tests.test_scan import cfg_for
    from collector.emit import hydrate, s3
    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "pdc-networks"}))
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
        assert result["data"]["pdc_networks"] == {"obs-hub": {"available": True, "network_count": 1}}
        assert result["meta"]["sources"]["pdc_networks"]["healthy"]
        assert result["_emit"]["views"]["pdc_networks"] == [ROW]
    else:
        assert "pdc_networks" not in result["data"]
        assert not result["meta"]["sources"]["pdc_networks"]["healthy"]
        assert "pdc_networks" not in result["_emit"]["views"]
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
        s3.write_views(views, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    if measured:
        envelope = json.loads(writes["views/pdc_networks.json"])
        assert envelope["rows"] == [ROW]
        assert envelope["meta"]["inputs"]["pdc_networks"]["source"] == "own"
        assert envelope["meta"]["inputs"]["pdc_networks"]["tier"] == "t2"
    else:
        assert "views/pdc_networks.json" not in writes
    diagnostic = tmp_path / "diagnostic.json"
    diagnostic.write_text(json.dumps(scan.label_risk_pillar.diagnostic_scan(result), default=str))
    event = scan.loki.summary_event("t2", result["meta"])
    assert PRIVATE not in diagnostic.read_text() + json.dumps(event) + json.dumps(result) + json.dumps(writes) + caplog.text + capsys.readouterr().out
    from bin import dashboards
    _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "pdc_networks.json" in json.dumps(assembled)


def test_default_off_exact_grants_and_retirement():
    from collector import provision as pr
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), mock.patch.object(scan.credentials, "load_all") as store:
        client = mock.Mock()
        assert scan.gather_pdc_networks(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        client.get.assert_not_called()
        store.assert_not_called()
    pairs = frozenset({("grafana-pdc-app.private-networks:read", ""),
                       ("plugins.app:access", "plugins:id:grafana-pdc-app")})
    assert pr.product_read_pairs({"pdc-networks"}) == pairs
    baseline = pr.permission_pairs(pr.desired_permissions(write_stack=False))
    selected = pr.permission_pairs(pr.desired_permissions(write_stack=False, product_reads={"pdc-networks"}))
    assert selected - baseline == pairs
    assert pairs <= pr.removable_pairs(write_stack=False)
    assert not (pairs & pr.removable_pairs(write_stack=False, product_reads={"pdc-networks"}))
    assert not any(action == "datasources:query" or "write" in action for action, _ in pairs)
    assert pr.dangerous_extra_pairs({"datasources:query": ["datasources:*"]}, selected)


def test_regions_attribution_empty_new_departed_and_limited():
    from collector.sources import pdc_networks as source, gcom
    from collector.pillars import compose
    from collector.coverage import Coverage
    calls = []
    estate = [STACK, {**STACK, "slug": "added", "regionSlug": "newer-region"}]
    records = source.probe_all(client_for(calls=calls), [STACK],
        {"obs-hub": {"token": "synthetic"}, "departed": {"token": "synthetic"}}, inventory=estate)
    assert records == {"obs-hub": {"available": True, "network_count": 1}}
    assert {parse_qs(urlsplit(url).query)["region"][0] for url in calls} == set(gcom.policy_regions(estate))
    assert set(gcom.POLICY_REALMS) | {"new-region", "newer-region"} == set(gcom.policy_regions(estate))
    empty = {"items": [], "metadata": {"pagination": {"nextPage": None}}}
    assert source.fetch_pdc_networks(client_for(empty), STACK, "synthetic", gcom.policy_regions([STACK])) == {"available": True, "network_count": 0}
    records["departed"] = records["obs-hub"]
    views = compose.build_all(estate, Coverage(tier="t2", total=2), pdc_networks=records)[1]
    assert views["pdc_networks"] == [ROW]
    assert "pdc_networks" not in compose.build_all([], Coverage(tier="t2", total=0), pdc_networks=records)[1]
    joined = source.probe_all(client_for(), estate, {"obs-hub": {"token": "synthetic"}})
    assert joined["added"] == {"available": False, "reason": "no_credential"}
    client = mock.Mock()
    assert not source.probe_all(client, [{**STACK, "regionSlug": None}], {})["obs-hub"]["available"]
    client.get.assert_not_called()


@pytest.mark.parametrize("change", [
    {"realms": None}, {"realms": []}, {"realms": [{}]},
    {"realms": [{"type": "unknown", "identifier": "123"}]},
    {"realms": [{"type": "stack", "identifier": True}]},
    {"realms": [{"type": "stack", "identifier": "*"}]},
    {"scopes": None}, {"scopes": [None]}, {"id": ""}, {"id": 123},
    {"config": {"password": PRIVATE}}, {"access_token": PRIVATE},
])
def test_malformed_identity_realm_scope_and_credentials_absent(change, capsys, caplog):
    from collector.sources import pdc_networks as source
    from collector.pillars import pdc_networks as pillar
    body = deepcopy(BODY)
    body["items"][0].update(change)
    errors = []
    records = source.probe_all(client_for(body), [STACK], {"obs-hub": {"token": "synthetic"}}, on_error=lambda slug, msg: errors.append(msg))
    assert records["obs-hub"]["available"] is False
    assert pillar.build([STACK], records) == ([], {})
    assert PRIVATE not in json.dumps([records, errors]) + caplog.text + capsys.readouterr().out


@pytest.mark.parametrize("body,status", [
    ({"items": []}, 200), ({"items": [], "metadata": {}}, 200),
    ({**BODY, "partial": False}, 200),
    ({"items": [], "metadata": {"pagination": {"nextPage": None, "total": 1}}}, 200),
    ({"items": [None], "metadata": BODY["metadata"]}, 200),
    (BODY, 206), (BODY, 302), (BODY, 401), (BODY, 403), (BODY, 500),
])
def test_unknown_partial_and_status_absent(body, status):
    from collector.sources import pdc_networks as source
    assert not source.fetch_pdc_networks(client_for(body, status), STACK, "synthetic", ["new-region"])["available"]


def test_complete_pages_rebuilt_deduplicated_and_late_region_failure():
    from collector.sources import pdc_networks as source
    from collector.config import GCOM
    calls = []
    def transport(request, timeout):
        calls.append(request.full_url)
        parsed = urlsplit(request.full_url)
        assert parsed.path == PATH and parsed.netloc == "inventory.example.test"
        query = parse_qs(parsed.query)
        assert query["realmType"] == ["stack"] and query["realmIdentifier"] == ["123"]
        body = deepcopy(BODY)
        if "pageCursor" not in query:
            body["metadata"]["pagination"]["nextPage"] = GCOM + "/v1/accesspolicies?pageCursor=next&region=" + query["region"][0]
        else:
            assert query["pageCursor"] == ["next"]
        return Response(200, json.dumps(body).encode(), request.full_url)
    record = source.fetch_pdc_networks(ReadOnlyClient(transport=transport), STACK, "synthetic", ["new-region", "us"])
    assert record == {"available": True, "network_count": 1}
    assert len(calls) == 4
    late = mock.Mock()
    late.get.side_effect = [Response(200, json.dumps(BODY).encode(), ""), Response(403, b"{}", "")]
    assert source.fetch_pdc_networks(late, STACK, "synthetic", ["new-region", "us"]) == {"available": False, "reason": "unreadable"}


@pytest.mark.parametrize("link", [
    "https://attacker.test/api/v1/accesspolicies?pageCursor=x",
    "https://grafana.com/api/v1/tokens?pageCursor=x",
    "https://user@grafana.com/api/v1/accesspolicies?pageCursor=x",
    "https://grafana.com/api/v1/accesspolicies?pageCursor=x#fragment",
    "v1/accesspolicies?pageCursor=x&region=other",
    "v1/accesspolicies?pageCursor=x&realmType=org",
    "v1/accesspolicies?pageCursor=x&realmIdentifier=456",
    "v1/accesspolicies?pageCursor=x&pageCursor=y",
    "v1/accesspolicies?pageCursor=x&unknown=y",
    "v1/%61ccesspolicies?pageCursor=x", "v1/accesspolicies?region=us",
    "v1/accesspolicies?pageCursor=", "", 1,
])
def test_unsafe_unsupported_continuation_never_requested(link):
    from collector.sources import pdc_networks as source
    body = deepcopy(BODY)
    body["metadata"]["pagination"]["nextPage"] = link
    calls = []
    result = source.fetch_pdc_networks(client_for(body, calls=calls), STACK, "synthetic", ["new-region"])
    assert not result["available"]
    assert len(calls) == 1


def test_loop_bounds_transport_store_and_structural_guard():
    from collector.sources import pdc_networks as source, resource_schema
    body = deepcopy(BODY)
    body["metadata"]["pagination"]["nextPage"] = "v1/accesspolicies?pageCursor=repeat"
    calls = []
    assert not source.fetch_pdc_networks(client_for(body, calls=calls), STACK, "synthetic", ["new-region"])["available"]
    assert len(calls) == 2
    with mock.patch.object(source, "MAX_PAGES", 1):
        assert source.fetch_pdc_networks(client_for(body), STACK, "synthetic", ["new-region"])["reason"] == "limit_exceeded"
    with mock.patch.object(source, "MAX_POLICIES", 0):
        assert source.fetch_pdc_networks(client_for(), STACK, "synthetic", ["new-region"])["reason"] == "limit_exceeded"
    for bound in ("MAX_DEPTH", "MAX_NODES"):
        with mock.patch.object(resource_schema, bound, 1):
            assert source.fetch_pdc_networks(client_for(), STACK, "synthetic", ["new-region"])["reason"] == "unsafe_schema"
    client = mock.Mock()
    client.get.side_effect = RuntimeError(PRIVATE)
    assert source.fetch_pdc_networks(client, STACK, "synthetic", ["us"]) == {"available": False, "reason": "transport_error"}
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "pdc-networks"}), mock.patch.object(scan.credentials, "load_all", side_effect=scan.credentials.StoreUnavailable(PRIVATE)):
        assert scan.gather_pdc_networks(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, ["pdc_networks: credential_store_unavailable"])


@pytest.mark.parametrize("url", ["http://host.test", "https://u:p@host.test", "https://host.test/?x=y", "https://host.test/#x", "https://host.test/%61pi"])
def test_origin_rejected(url):
    from collector.sources import pdc_networks as source
    client = mock.Mock()
    assert source.fetch_pdc_networks(client, {**STACK, "url": url}, "synthetic", ["us"]) == {"available": False, "reason": "invalid_url"}
    client.get.assert_not_called()


@pytest.mark.parametrize("stack_id", [None, True, 0, -1, 1.0, "123/escape", "123?x=y", "01", "1" * 21])
def test_stack_id_rejected_before_credential(stack_id):
    from collector.sources import pdc_networks as source
    client = mock.Mock()
    assert source.fetch_pdc_networks(client, {**STACK, "id": stack_id}, "synthetic", ["us"]) == {"available": False, "reason": "invalid_stack_id"}
    client.get.assert_not_called()


def test_real_redirect_never_forwards_reader(monkeypatch):
    from collector.sources import pdc_networks as source
    from tests.test_slo_inventory import wire, WireBody
    calls = wire(monkeypatch, lambda req: (302, {"Location": "https://attacker.test/capture"}, WireBody(b"")))
    assert source.fetch_pdc_networks(ReadOnlyClient(max_attempts=1), STACK, "synthetic", ["us"])["reason"] == "unreadable"
    assert len(calls) == 1


def test_optional_missing_retained_age_and_fixture_preservation():
    from bin import dashboards, make_compose_fixture
    from collector.dashboards import build
    real_read = build.read_view
    def missing(name):
        if name == "pdc_networks":
            raise FileNotFoundError(name)
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=missing):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "pdc_networks.json" not in json.dumps(assembled)
    assert "cloud_accounts.json" in json.dumps(assembled)
    assert "_age_pdc_networks" in assembled["spec"]["elements"]
    def retained(name):
        return {"meta": {"generated_at": "2020-01-01T00:00:00Z"}, "rows": [ROW]} if name == "pdc_networks" else real_read(name)
    with mock.patch.object(build, "read_view", side_effect=retained):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "pdc_networks.json" in json.dumps(assembled)
    assert "time()" in json.dumps(assembled["spec"]["elements"]["_age_pdc_networks"])
    original = make_compose_fixture.COMMITTED_FIXTURE.read_bytes()
    assert make_compose_fixture.main(["--synthetic-pdc"]) == 0
    assert make_compose_fixture.COMMITTED_FIXTURE.read_bytes() == original


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("transport"), json.JSONDecodeError("invalid", "", 0)])
def test_optional_access_parse_errors_explicit(error):
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    def read(name):
        if name == "pdc_networks":
            raise error
        return real_read(name)
    with mock.patch.object(build, "read_view", side_effect=read), pytest.raises(type(error)):
        dashboards.assemble("usage", "infinity-uid")
