"""Library counts through the real T2 orchestration and S3 publication boundary (offline)."""
import datetime as dt
import json
from pathlib import Path
from contextlib import ExitStack, contextmanager
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector.coverage import Coverage
from collector.emit import hydrate, s3
from collector.pillars import compose
from tests.test_library_panels import PRIVATE, STACK, client_for, page
from tests.test_scan import cfg_for

INPUT = "library_panels_inventory"
ROW = {"Stack": "current", "Configured library panels": 2}


@contextmanager
def scan_edges(stacks, policy="library-panels"):
    """Replace only other sources and external stores; library source/composition/emission are real."""
    fixture = json.loads((Path(__file__).parent / "fixtures/compose_inputs.json").read_text())
    records = {s["slug"]: {"available": True, "slug": s["slug"]}
               for s in stacks if s.get("status") != "paused"}
    def detail(_client, _cfg, selected, coverage, *, on_error):
        for stack in selected:
            if stack.get("status") == "paused":
                coverage.record_skipped(stack["slug"], "paused")
            else:
                coverage.record_ok(stack["slug"])
        return {slug: {"users": []} for slug in records}
    with ExitStack() as edges:
        edges.enter_context(mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": policy}))
        store = edges.enter_context(mock.patch.object(scan.credentials, "load_all", return_value={
            "current": {"token": "synthetic"}, "departed": {"token": "synthetic"}}))
        inventory = edges.enter_context(mock.patch.object(scan.gcom, "fetch_inventory", return_value=stacks))
        edges.enter_context(mock.patch.object(scan.gcom, "fetch_all_stack_detail", side_effect=detail))
        edges.enter_context(mock.patch.object(scan.plugin_catalog, "fetch_catalogue", return_value={}))
        for name in ("assistant", "insights", "dashboard_inventory", "datasource_query_cost", "adaptive_logs",
                     "adaptive_traces", "public_dashboards", "alert_routing", "signal_inventory"):
            source_fixture = fixture[name]
            sample = source_fixture.get("obs-hub", next(iter(source_fixture.values()), {}))
            data = {slug: dict(sample, available=True, slug=slug) for slug in records}
            edges.enter_context(mock.patch.object(scan, "gather_" + name, return_value=(data, [])))
        edges.enter_context(mock.patch.object(scan, "gather_service_accounts", return_value=(
            {slug: {"state": "ok"} for slug in records}, [])))
        edges.enter_context(mock.patch.object(scan, "gather_capability_adoption", return_value=({"available": True}, [])))
        edges.enter_context(mock.patch.object(scan, "gather_loki_config", return_value=(
            {slug: {"limits": {"available": True}, "change_requests": {"available": True}} for slug in records}, [])))
        edges.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value=records))
        edges.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        edges.enter_context(mock.patch.object(hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1)))
        yield store, inventory


def test_default_off_before_extra_credential_or_http_calls():
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": ""}), \
            mock.patch.object(scan.credentials, "load_all") as store:
        client = mock.Mock()
        assert scan.gather_library_panels_inventory(client, SimpleNamespace(concurrency=1), [STACK]) == ({}, [])
        store.assert_not_called()
        client.get.assert_not_called()
    with scan_edges([STACK], policy="") as (store, inventory):
        result = scan.run_t2(mock.Mock(), cfg_for())
    store.assert_not_called()
    inventory.assert_called_once()
    assert INPUT not in result["_emit"]["views"]
    assert result["meta"]["sources"][INPUT]["reason"] == "not_selected"


@pytest.mark.parametrize("responses,measured,count", [
    ([(page([1, 2]), 200)], True, 2), ([(page([]), 200)], True, 0),
    ([(page(range(1, 101), total=101), 200), (page([101], 2, 101), 200)], True, 101),
    ([(page([1, 2]), 206)], False, None),
    ([(page(range(1, 101), total=101), 200), (page([100], 2, 101), 200)], False, None),
    ([(page(range(1, 101), total=101), 200), ({"error": PRIVATE}, 403)], False, None),
])
def test_scan_to_real_s3_boundary_and_diagnostic_minimization(responses, measured, count, tmp_path, capsys, caplog):
    calls = []
    client = client_for(responses, calls)
    # A missing/new stack is not invented by payload keys; departed credentials are never read.
    with scan_edges([STACK, {"slug": "paused", "status": "paused"}]) as (store, inventory):
        result = scan.run_t2(client, cfg_for())
        store.assert_called_once()
        inventory.assert_called_once()
        writes = {"views/library_panels_inventory.json": "last-good"}
        def put(path, key, bucket, dry_run):
            writes[key] = path.read_text()
            return key
        # Exercise run(), the actual CLI publication path, using the freshly gathered result.
        with mock.patch.object(scan, "run_t2", return_value=result), mock.patch.object(s3, "_put", side_effect=put), \
                mock.patch.object(scan.mimir.RemoteWriter, "push", return_value=0), \
                mock.patch.object(scan.loki.LokiWriter, "push", return_value=0):
            output = tmp_path / "diagnostic.json"
            exit_code = scan.run(client, cfg_for(), SimpleNamespace(out=str(output)))
    assert exit_code == (0 if measured else 1)
    assert result["meta"]["sources"][INPUT]["healthy"] == measured
    if measured:
        expected = {"Stack": "current", "Configured library panels": count}
        assert result["data"][INPUT] == {"current": {"available": True, "library_panel_count": count}}
        view = json.loads(writes["views/library_panels_inventory.json"])
        assert view["rows"] == [expected]
        assert view["meta"]["inputs"][INPUT]["source"] == "own"
        assert view["meta"]["inputs"][INPUT]["tier"] == "t2"
        assert view["meta"]["inputs"][INPUT]["schema_version"] == 1
        assert "scans/t2/latest.json" in writes
        assert INPUT in json.loads(writes["scans/t2/latest.json"])["data"]
        assert PRIVATE not in output.read_text()
    else:
        assert INPUT not in result["data"]
        assert INPUT not in result["_emit"]["views"]
        assert writes == {"views/library_panels_inventory.json": "last-good"}
    captured = capsys.readouterr()
    assert PRIVATE not in json.dumps(result, default=str) + json.dumps(writes) + captured.out + captured.err + caplog.text
    assert calls[0].endswith("/api/access-control/user/permissions")
    assert all("departed" not in call for call in calls)


def test_local_scan_cli_runs_real_source_and_sanitized_diagnostic(tmp_path, capsys):
    output = tmp_path / "cli-diagnostic.json"
    calls = []
    client = client_for([(page([1, 2]), 200)], calls)
    with scan_edges([STACK]), mock.patch.object(scan.config, "load", return_value=cfg_for()), \
            mock.patch.object(scan, "ReadOnlyClient", return_value=client):
        assert scan.main(["--tier", "t2", "--dry-run", "--out", str(output)]) == 0
    document = json.loads(output.read_text())
    assert document["data"][INPUT] == {"current": {"available": True, "library_panel_count": 2}}
    assert document["meta"]["sources"][INPUT]["available"] == 1
    assert len(calls) == 2
    captured = capsys.readouterr()
    assert PRIVATE not in output.read_text() + captured.out + captured.err


def test_missing_coverage_unknown_inventory_and_sanitized_store_error(capsys):
    with scan_edges([STACK]):
        result = scan.run_t2(client_for([], permissions={}), cfg_for())
    assert INPUT not in result["data"]
    assert INPUT not in result["_emit"]["views"]
    with scan_edges([]):
        result = scan.run_t2(mock.Mock(), cfg_for())
    assert not result["meta"]["inputs"][INPUT]["available"]
    assert INPUT not in result["_emit"]["views"]
    with mock.patch.dict("os.environ", {"GCINSIGHT_READER_PRODUCT_READS": "library-panels"}), \
            mock.patch.object(scan.credentials, "load_all", side_effect=scan.credentials.StoreUnavailable(PRIVATE)):
        assert scan.gather_library_panels_inventory(mock.Mock(), SimpleNamespace(concurrency=1), [STACK]) == (
            {}, ["library_panels_inventory: credential_store_unavailable"])
    assert PRIVATE not in capsys.readouterr().err


def test_fresh_inventory_left_join_and_no_product_metrics():
    records = {"current": {"available": True, "library_panel_count": 2},
               "departed": {"available": True, "library_panel_count": 123},
               "unknown": {"available": False, "library_panel_count": 0}}
    stacks = [STACK, {"slug": "unknown"}, {"slug": "new"}, {"slug": "paused", "status": "paused"}]
    cov = Coverage(tier="t2", total=len(stacks))
    metrics, views, _ = compose.build_all(stacks, cov, **{INPUT: records})
    baseline, _, _ = compose.build_all(stacks, cov)
    assert metrics == baseline
    assert views[INPUT] == [ROW]
    assert INPUT not in compose.build_all([], Coverage(tier="t2", total=0), **{INPUT: records})[1]


def test_hydration_version_freshness_withholding_and_never_own_input():
    now = dt.datetime(2026, 10, 5, tzinfo=dt.timezone.utc)
    payload = {"current": {"available": True, "library_panel_count": 2}}
    previous = {"meta": {"tier": "t2", "generated_at": (now - dt.timedelta(hours=2)).isoformat(),
                         "inputs": {INPUT: {"schema_version": 1}}}, "data": {INPUT: payload}}
    loader = lambda tier, bucket: previous if tier == "t2" else None
    inputs, prov = hydrate.hydrate("t1", {}, now=now, loader=loader)
    assert inputs[INPUT] == payload
    assert prov[INPUT]["age_seconds"] == 7200
    assert prov[INPUT]["schema_version"] == 1
    assert hydrate.filter_views({INPUT: [ROW]}, prov)[0] == {INPUT: [ROW]}
    _, own = hydrate.hydrate("t2", {}, now=now, loader=loader)
    assert not own.satisfied(INPUT)
    assert hydrate.filter_views({INPUT: [ROW]}, own)[0] == {}
    previous["meta"]["inputs"][INPUT]["schema_version"] = 2
    inputs, prov = hydrate.hydrate("t1", {}, now=now, loader=loader)
    assert INPUT not in inputs
    assert prov[INPUT]["state"] == "incompatible_schema"
    previous["meta"]["inputs"][INPUT]["schema_version"] = 1
    previous["meta"]["generated_at"] = (now - hydrate.MAX_INPUT_AGE - dt.timedelta(seconds=1)).isoformat()
    inputs, prov = hydrate.hydrate("t1", {}, now=now, loader=loader)
    assert INPUT not in inputs
    assert not prov.satisfied(INPUT)
