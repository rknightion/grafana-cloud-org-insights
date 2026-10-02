"""Projected IRM counts across the real GET, scan, compose and publication boundaries."""
import json
from pathlib import Path
from contextlib import ExitStack
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
PATH = "/api/plugins/grafana-irm-app/resources/alert_receive_channels/counters/"
SENTINEL = "opaque-sensitive-sentinel"


def client_for(body, status=200, calls=None):
    def transport(request, timeout):
        if calls is not None:
            calls.append(request.full_url)
        assert request.method == "GET"
        assert request.full_url == STACK["url"] + PATH
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


def test_projected_count_public_boundary(tmp_path, capsys, caplog):
    body = json.loads((Path(__file__).parent / "fixtures/irm_counters.json").read_text())
    from tests.test_scan import cfg_for

    def detail(_client, _cfg, selected, coverage, *, on_error):
        coverage.record_ok("obs-hub")
        return {}

    # Unrelated external gatherers have no data in this focused estate. Keep the
    # selected IRM gatherer, hydration, composition and publication real.
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "irm-integrations"}))
        edges.enter_context(mock.patch.object(scan.credentials, "load_all", return_value={
            "obs-hub": {"token": "synthetic-token"}, "departed": {"token": "synthetic-token"}}))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_inventory", return_value=[STACK]))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail))
        for name in ("service_accounts", "assistant", "insights", "dashboard_inventory",
                     "datasource_query_cost", "adaptive_logs", "adaptive_traces", "public_dashboards",
                     "alert_routing", "slo_inventory", "signal_inventory", "capability_adoption", "loki_config"):
            edges.enter_context(mock.patch.object(scan, "gather_" + name, return_value=({}, [])))
        edges.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value={}))
        edges.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        edges.enter_context(mock.patch.object(hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1)))
        result = scan.run_t2(client_for(body), cfg_for())
    data = result["data"]["irm_integrations"]
    errors = result["meta"]["error_samples"]
    assert data == {"obs-hub": {"available": True, "integration_count": 1}}
    assert errors == []
    metrics, views = result["_emit"]["metrics"], result["_emit"]["views"]
    assert views["irm_integrations"] == [{"Stack": "obs-hub", "Configured IRM integrations": 1}]
    assert not any("irm" in name for name, _, _ in metrics)
    report = result["meta"]["sources"]["irm_integrations"]
    assert report["healthy"]
    writes = {}
    def put(path, key, bucket, dry_run):
        writes[key] = path.read_text()
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        filtered, _ = hydrate.filter_views(views, result["meta"]["inputs"])
        s3.write_views(filtered, result["meta"], view_coverage=result["_emit"]["view_coverage"])
    envelope = json.loads(writes["views/irm_integrations.json"])
    assert envelope["rows"] == views["irm_integrations"]
    assert envelope["meta"]["inputs"]["irm_integrations"]["source"] == "own"
    assert envelope["meta"]["inputs"]["irm_integrations"]["tier"] == "t2"
    encoded = json.dumps({"data": data, "errors": errors, "views": envelope, "report": report})
    assert SENTINEL not in encoded + capsys.readouterr().out + caplog.text
    assert "alerts_count" not in encoded and "alert_groups_count" not in encoded
    from bin import dashboards
    uid, assembled = dashboards.assemble("usage", "infinity-uid")
    assert uid == "gcinsight-usage"
    panel_json = json.dumps(assembled)
    assert "irm_integrations.json" in panel_json
    assert "Configured IRM integrations" in panel_json


def test_selection_and_exact_grants():
    calls = []
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), \
            mock.patch.object(scan.credentials, "load_all") as creds:
        assert scan.gather_irm_integrations(client_for({}, calls=calls), SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        creds.assert_not_called()
    assert calls == []
    assert product_read_pairs({"irm-integrations"}) == frozenset({
        ("grafana-irm-app.integrations:read", ""),
        ("plugins.app:access", "plugins:id:grafana-irm-app")})
    baseline = desired_permissions(write_stack=False)
    selected = desired_permissions(write_stack=False, product_reads={"irm-integrations"})
    assert [p for p in baseline if p["action"] == "datasources:query"] == [
        p for p in selected if p["action"] == "datasources:query"]


@pytest.mark.parametrize("body,status", [({}, 200), ({SENTINEL: {"alerts_count": 0, "alert_groups_count": 0}}, 200)])
def test_valid_empty_and_zero_activity_count(body, status):
    from collector.sources import irm_integrations as source
    result = source.probe_all(client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic-token"}})
    assert result["obs-hub"] == {"available": True, "integration_count": len(body)}
    records = {**result, "departed": {"available": True, "integration_count": 99}}
    views = compose.build_all([STACK, {"slug": "added"}], Coverage(tier="t2", total=2), irm_integrations=records)[1]
    assert views["irm_integrations"] == [{"Stack": "obs-hub", "Configured IRM integrations": len(body)}]
    assert "irm_integrations" not in compose.build_all([], Coverage(tier="t2", total=0), irm_integrations=records)[1]


@pytest.mark.parametrize("body,status", [
    ([], 200), ({SENTINEL: {"alerts_count": True, "alert_groups_count": 0}}, 200),
    ({SENTINEL: {"alerts_count": -1, "alert_groups_count": 0}}, 200),
    ({SENTINEL: {"alerts_count": 1.0, "alert_groups_count": 0}}, 200),
    ({SENTINEL: {"alerts_count": 0}}, 200),
    ({SENTINEL: {"alerts_count": 0, "alert_groups_count": 0, "config": SENTINEL}}, 200),
    ({"error": SENTINEL}, 403), ({"error": SENTINEL}, 500),
])
def test_failed_or_partial_is_absent_and_private(body, status, capsys, caplog):
    from collector.sources import irm_integrations as source
    errors = []
    result = source.probe_all(client_for(body, status), [STACK], {"obs-hub": {"token": "synthetic-token"}}, on_error=lambda slug, msg: errors.append(msg))
    assert result["obs-hub"]["available"] is False
    views = compose.build_all([STACK], Coverage(tier="t2", total=1), irm_integrations=result)[1]
    assert "irm_integrations" not in views
    assert SENTINEL not in json.dumps([result, errors]) + capsys.readouterr().out + caplog.text


@pytest.mark.parametrize("url", ["http://host.test", "https://u:p@host.test", "https://host.test/?x=y", "https://host.test/#x", "https://host.test/%61pi"])
def test_origin_rejected_before_transport(url):
    from collector.sources import irm_integrations as source
    calls = []
    result = source.probe_all(client_for({}, calls=calls), [{**STACK, "url": url}], {"obs-hub": {"token": "synthetic-token"}})
    assert not result["obs-hub"]["available"]
    assert calls == []


def test_usage_assembly_without_never_published_irm_view():
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    reads = []

    def read(name):
        reads.append(name)
        if name == "irm_integrations":
            raise FileNotFoundError("views/irm_integrations.json: never published")
        return real_read(name)

    with mock.patch.object(build, "read_view", side_effect=read):
        uid, assembled = dashboards.assemble("usage", "infinity-uid")
    assert uid == "gcinsight-usage"
    assert any(name != "irm_integrations" for name in reads)
    assert "irm_integrations.json" not in json.dumps(assembled)
    assert "irm_integrations" not in assembled["spec"]["elements"]
    # Shared freshness guidance remains; only the optional table and its dedicated tab are omitted.
    assert "Configured IRM integrations" not in [
        tab["spec"]["title"] for tab in assembled["spec"]["layout"]["spec"]["tabs"]
    ]


def test_usage_assembly_keeps_readable_retained_irm_view():
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view
    retained = {"meta": {"generated_at": "2020-01-01T00:00:00Z"},
                "rows": [{"Stack": "obs-hub", "Configured IRM integrations": 1}]}

    def read(name):
        return retained if name == "irm_integrations" else real_read(name)

    with mock.patch.object(build, "read_view", side_effect=read):
        _, assembled = dashboards.assemble("usage", "infinity-uid")
    assert "irm_integrations.json" in json.dumps(assembled)
    assert "Configured IRM integrations" in json.dumps(assembled)


@pytest.mark.parametrize("error", [PermissionError("denied"), RuntimeError("transport"),
                                        json.JSONDecodeError("invalid", "", 0)])
def test_usage_assembly_does_not_hide_irm_read_failures(error):
    from bin import dashboards
    from collector.dashboards import build
    real_read = build.read_view

    def read(name):
        if name == "irm_integrations":
            raise error
        return real_read(name)

    with mock.patch.object(build, "read_view", side_effect=read), pytest.raises(type(error)):
        dashboards.assemble("usage", "infinity-uid")


@pytest.mark.parametrize("stderr,expected", [
    ('fatal error: An error occurred (404) when calling the HeadObject operation: Key "views/irm_integrations.json" does not exist', FileNotFoundError),
    ('An error occurred (NoSuchKey) when calling the GetObject operation: missing', FileNotFoundError),
    ('fatal error: An error occurred (403) when calling the HeadObject operation: Forbidden', RuntimeError),
    ('Could not connect to the endpoint URL', RuntimeError),
    ('An error occurred (NoSuchBucket) when calling the HeadObject operation: missing', RuntimeError),
])
def test_view_source_classifies_only_missing_object_as_absent(stderr, expected):
    from collector.dashboards import build
    with mock.patch.object(build, "VIEWS_DIR", ""), mock.patch.object(build, "BUCKET", "synthetic"), \
            mock.patch.object(build.subprocess, "run", return_value=SimpleNamespace(returncode=1, stderr=stderr)), \
            pytest.raises(expected):
        build.read_view("irm_integrations")
