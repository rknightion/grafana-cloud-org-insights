"""Offline scan/publication seams for D-VOL20 and D-RULE20; no live estate."""
from __future__ import annotations

import copy
import datetime as dt
import json
import os
import pathlib
import sys
from types import SimpleNamespace
from unittest import mock

import pytest

import scan
from collector import config, identity
from collector.coverage import Coverage
from collector.emit import budget, hydrate
from collector.httpclient import ReadOnlyClient, Response
from collector.pillars import compose
from collector.sources import loki_volume, rule_inventory

ROOT = pathlib.Path(__file__).resolve().parents[1]
SERVICE = "private-service-canary"
SECRET = "discard-rule-private-canary"
FLAGS = {"GCINSIGHT_LOKI_VOLUME_ENABLED": "0", "GCINSIGHT_RULE_INVENTORY_ENABLED": "0"}
STACK = {"slug": "synthetic", "status": "active", "hlInstanceUrl": "https://logs.example.test",
         "hlInstanceId": 7000001, "hmInstancePromUrl": "https://metrics.example.test",
         "hmInstancePromId": 6000001, "amInstanceUrl": "https://alerts.example.test",
         "amInstanceId": 9000001}


def client_for(*, failed=(), empty=False):
    calls = []
    def transport(request, timeout):
        from urllib.parse import urlsplit, parse_qs
        path = urlsplit(request.full_url).path
        calls.append(path)
        assert request.method == "GET"
        assert "/status" not in path and "/config" not in path
        if path == loki_volume.PATH:
            params = parse_qs(urlsplit(request.full_url).query)
            assert params["limit"] == ["100"] and params["targetLabels"] == ["service_name"]
            assert int(params["end"][0]) - int(params["start"][0]) == 86400 * 10**9
            body = {"status": "success", "data": {"resultType": "vector", "result": [] if empty else [
                {"metric": {"service_name": SERVICE}, "value": [1, "23"]}]}}
        elif path.endswith("/rules"):
            body = {"status": "success", "data": {"groups": [] if empty else [{"name": SECRET, "rules": [
                {"type": "alerting", "name": SECRET, "query": SECRET, "labels": {"x": SECRET}},
                {"type": "recording", "name": SECRET, "query": SECRET}]}]}}
        elif path == "/api/prom/api/v1/alerts":
            body = {"status": "success", "data": {"alerts": [] if empty else [{"state": "firing", "labels": {"x": SECRET}}]}}
        else:
            assert path in ("/alertmanager/api/v2/alerts", "/alertmanager/api/v2/silences")
            body = [] if empty else [{"status": {"state": "active"}, "labels": {"x": SECRET}, "matchers": [SECRET], "receiver": SECRET}]
        return Response(503 if path in failed else 200, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1, deadline=30), calls


def inputs_for(stacks=None, **kwargs):
    stacks = [STACK] if stacks is None else stacks
    client, calls = client_for(**kwargs)
    return {"loki_volume": loki_volume.probe_all(client, stacks, "synthetic", enabled=True),
            "rule_inventory": rule_inventory.probe_all(client, stacks, "synthetic", enabled=True)}, calls


def build(inputs, stacks=None):
    stacks = [STACK] if stacks is None else stacks
    cov = Coverage(tier="t2", total=len(stacks))
    for stack in stacks:
        cov.record_ok(stack["slug"])
    return compose.build_all(stacks, cov, **inputs)


def test_new_scan_flags_are_digest_bound_and_old_defaultoff_digest_works():
    from tests.test_consumer_manifest import fixture, consumer_manifest
    body = fixture()
    for flag in FLAGS:
        body["runtime"]["scan"].pop(flag, None)
    body["overlay_digest"], body["runtime_projection_digests"] = consumer_manifest.calculated_digests(body)
    consumer_manifest.validate(body)
    old_digest = body["runtime_projection_digests"]["scan"]
    env = {**body["runtime"]["scan"], **FLAGS, "GCINSIGHT_RUNTIME_CONFIG_DIGEST": old_digest}
    assert identity.verify_runtime_projection("scan", environ=env) == old_digest
    for flag in FLAGS:
        enabled = {**env, flag: "1"}
        assert identity.projection_digest("scan", enabled) != identity.projection_digest("scan", env)
        with pytest.raises(identity.InvalidIdentity):
            identity.verify_runtime_projection("scan", environ=enabled)
        selected = copy.deepcopy(body)
        selected["runtime"]["scan"][flag] = "1"
        selected = consumer_manifest.regenerate(selected)
        consumer_manifest.validate(selected)
    assert consumer_manifest.calculated_digests(body)[0] == body["overlay_digest"]


def test_disabled_config_zero_calls_and_no_hydration_revival():
    with mock.patch.dict(os.environ, {}, clear=True):
        assert config._optional_bool(config.LOKI_VOLUME_ENV) is False
        assert config._optional_bool(config.RULE_INVENTORY_ENV) is False
    cfg = SimpleNamespace(cap="synthetic", loki_volume_enabled=False, rule_inventory_enabled=False)
    client = mock.Mock()
    for name in ("loki_volume", "rule_inventory"):
        assert getattr(scan, "gather_" + name)(client, cfg, [STACK]) == ({}, [])
        assert name in scan.disabled_inputs(cfg)
        assert hydrate.INPUT_OWNER[name] == "t2"
    client.get.assert_not_called()
    loader = mock.Mock(return_value={"data": inputs_for()[0], "meta": {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat()}})
    own, prov = hydrate.hydrate("t2", {}, enabled={"loki_volume", "rule_inventory"}, loader=loader)
    for name in ("loki_volume", "rule_inventory"):
        assert name not in own and not prov.satisfied(name)


def test_compose_private_volume_unknown_total_and_independent_rule_counts():
    inputs, calls = inputs_for(failed=("/api/prom/api/v1/alerts",))
    metrics, views, _ = build(inputs)
    row = views["loki_volume_top_services"][0]
    assert row["Service"] == SERVICE and row["Bytes"] == 23
    assert row["Total bytes"] is None and row["Other bytes"] is None
    assert row["Limit"] == 100 and row["Window seconds"] == 86400
    mimir = next(r for r in views["alerting_rule_inventory"] if r["Family"] == "mimir")
    assert mimir["Alerting rules"] == 1 and mimir["Recording rules"] == 1
    assert mimir["Firing"] is None and mimir["Pending"] is None
    assert SECRET not in json.dumps(inputs) + json.dumps(views)
    assert SERVICE not in json.dumps(metrics)
    safe = scan.producer_diagnostic_scan({"data": inputs, "views": views, "_emit": {"views": views}})
    assert SERVICE not in json.dumps(safe)
    assert SERVICE in json.dumps(inputs), "diagnostic fence must not mutate private S3 input"
    assert set(calls) == {loki_volume.PATH, "/api/prom/api/v1/rules", "/api/prom/api/v1/alerts",
                          "/prometheus/api/v1/rules", "/alertmanager/api/v2/alerts", "/alertmanager/api/v2/silences"}
    assert all(not name.startswith(("gcinsight_loki_volume", "gcinsight_rule_inventory")) for name, _, _ in metrics)


def test_empty_or_unavailable_inputs_do_not_publish_zero_estate():
    inputs, _ = inputs_for(empty=True)
    _, views, _ = build(inputs)
    assert views["loki_volume_top_services"][0]["Bytes"] is None
    assert views["loki_volume_top_services"][0]["Returned producers"] == 0
    assert views["alerting_rule_inventory"][0]["Alerting rules"] == 0
    _, empty_views, _ = build(inputs, [])
    assert "loki_volume_top_services" not in empty_views and "alerting_rule_inventory" not in empty_views
    for name in ("loki_volume", "rule_inventory"):
        report = scan.producer_source_report(name, [], inputs[name], enabled=True)
        assert not report["healthy"] and report["state"] == "unavailable"
        good, bad = scan.publication_inputs({name: inputs[name]}, {name: report})
        assert name not in good and name in bad
        _, prov = hydrate.hydrate("t2", {}, unavailable=bad, loader=lambda *_: None)
        filtered, withheld = hydrate.filter_views(views, prov)
        view = "loki_volume_top_services" if name == "loki_volume" else "alerting_rule_inventory"
        assert view not in filtered and view in withheld


@pytest.mark.parametrize("rows", ["bad", [None], [{"service_name": SERVICE, "bytes": -1}],
                                   [{"service_name": SERVICE, "bytes": 2}] * 101])
def test_malformed_hydrated_volume_is_withheld_not_normalized_to_zero(rows):
    inputs, _ = inputs_for()
    inputs["loki_volume"]["stacks"][STACK["slug"]]["rows"] = rows
    _, views, _ = build(inputs)
    assert "loki_volume_top_services" not in views
    assert "alerting_rule_inventory" in views


def test_each_rule_route_floor_retains_known_peer_counts_at_ninety_percent():
    stacks = [{**STACK, "slug": f"synthetic-{i}"} for i in range(10)]
    inputs, _ = inputs_for(stacks)
    partial, _ = inputs_for([stacks[0]], failed=("/api/prom/api/v1/alerts",))
    inputs["rule_inventory"]["stacks"].update(partial["rule_inventory"]["stacks"])
    report = scan.producer_source_report("rule_inventory", stacks, inputs["rule_inventory"], enabled=True)
    assert report["healthy"] and report["routes"]["mimir_alerts"]["coverage_ratio"] == .9
    accepted, unavailable = scan.publication_inputs(inputs, {"rule_inventory": report})
    assert "rule_inventory" in accepted and not unavailable
    _, views, _ = build(accepted, stacks)
    row = next(r for r in views["alerting_rule_inventory"] if r["Stack"] == "synthetic-0" and r["Family"] == "mimir")
    assert row["Alerting rules"] == 1 and row["Firing"] is None and row["Response state"] == "partial"


def test_partial_rule_routes_obey_shared_floor_not_label_exception():
    inputs, _ = inputs_for(failed=("/alertmanager/api/v2/silences",))
    report = scan.producer_source_report("rule_inventory", [STACK], inputs["rule_inventory"], enabled=True)
    assert report["available"] == 4 and report["expected"] == 5
    assert not report["healthy"]
    assert scan.blocking_source_failures("t2", ["label_inventory", "rule_inventory", "loki_volume"]) == ["rule_inventory", "loki_volume"]
    good, bad = scan.publication_inputs(inputs, {"rule_inventory": report})
    assert "rule_inventory" not in good and "rule_inventory" in bad


@pytest.mark.parametrize("present", [(), ("GCINSIGHT_LOKI_VOLUME_ENABLED",), ("GCINSIGHT_RULE_INVENTORY_ENABLED",), tuple(FLAGS)])
def test_independent_defaultoff_flags_preserve_digest_when_ecs_adds_the_missing_peer(present):
    env = {name: "synthetic" for name in identity.SCAN_ENV
           if name not in identity.PRODUCER_RULE_DEFAULTS and name not in identity.LABEL_INVENTORY_DEFAULTS}
    env.update({name: "0" for name in present})
    digest = identity.projection_digest("scan", env)
    deployed = {**env, **FLAGS, **identity.LABEL_INVENTORY_DEFAULTS,
                "GCINSIGHT_RUNTIME_CONFIG_DIGEST": digest}
    assert identity.verify_runtime_projection("scan", environ=deployed) == digest
    for name in FLAGS:
        with pytest.raises(identity.InvalidIdentity):
            identity.verify_runtime_projection("scan", environ={**deployed, name: "1"})


def test_legacy_golden_manifest_projection_digests_are_unchanged():
    from tests.test_consumer_manifest import consumer_manifest
    for name in ("manifest-full.json", "manifest-distinct.json", "manifest-pruned.json"):
        body = json.loads((ROOT / "terraform/tests/fixtures" / name).read_text())
        consumer_manifest.validate(body)
        assert consumer_manifest.calculated_digests(body) == (body["overlay_digest"], body["runtime_projection_digests"])


@pytest.mark.parametrize("enabled", [False, True])
def test_real_config_flags_defaultoff_and_validation(enabled):
    env = {name: "synthetic" for name, _ in config.REQUIRED_ENV}
    env["GCINSIGHT_READ_TOKEN"] = "synthetic"
    if enabled:
        env.update({name: "true" for name in FLAGS})
    with mock.patch.dict(os.environ, env, clear=True):
        cfg = config.load(tier="t2", dry_run=True)
        assert cfg.loki_volume_enabled is enabled and cfg.rule_inventory_enabled is enabled
        assert cfg.redacted["loki_volume_enabled"] is enabled
    for name in FLAGS:
        with mock.patch.dict(os.environ, {**env, name: "invalid"}, clear=True):
            with pytest.raises(config.MissingConfig):
                config.load(tier="t2", dry_run=True)


def test_budget_adds_only_sixteen_planned_provenance_series():
    assert budget.INPUT == len(hydrate.INPUT_OWNER) == 32
    for view in ("loki_volume_top_services", "alerting_rule_inventory"):
        assert next(s for s in budget.CATALOGUE if s.name == view).store == "view"


def exercise_cli(tmp_path, *, failed=(), empty_estate=False, enabled=True, dry_run=True, limited=False):
    """Real scanner CLI, gather wrappers, frozen source GETs, composition and final sink fences."""
    import contextlib
    import io
    from urllib.parse import urlsplit
    source_client, calls = client_for(failed=failed)
    # Exercise the scanner's actual shared ReadOnlyClient with synthetic process-edge transport.
    transport = source_client._transport
    def http(request, timeout):
        if urlsplit(request.full_url).hostname == "grafana.com":
            body = {"items": [] if empty_estate else [STACK]} if urlsplit(request.full_url).path == "/api/instances" else {"items": []}
            return Response(200, json.dumps(body).encode(), request.full_url)
        return transport(request, timeout)
    env = {name: "synthetic" for name, _ in config.REQUIRED_ENV}
    env.update({"GCINSIGHT_READ_TOKEN": "synthetic", "GCINSIGHT_MIMIR_URL": "https://metrics.example.test",
                "GCINSIGHT_LOKI_URL": "https://logs.example.test"})
    env.update({name: str(int(enabled)) for name in FLAGS})
    healthy = {STACK["slug"]: {"available": True}}
    records, views, metrics, events, finding_inputs = [], [], [], [], []
    fixture = json.loads((ROOT / "tests/fixtures/compose_inputs.json").read_text())
    real_hydrate, real_derive = hydrate.hydrate, scan.findings_mod.derive
    stdout, stderr = io.StringIO(), io.StringIO()
    with contextlib.ExitStack() as patches:
        patches.enter_context(mock.patch.dict(os.environ, env, clear=True))
        patches.enter_context(mock.patch.object(scan, "ReadOnlyClient", side_effect=lambda **kw: ReadOnlyClient(transport=http, **kw)))
        patches.enter_context(mock.patch.object(scan, "_verified_ecs_runtime", return_value=True))
        patches.enter_context(mock.patch.object(scan.label_risk_src, "probe_all", return_value=healthy))
        patches.enter_context(mock.patch.object(scan, "gather_label_inventory", return_value=({}, [])))
        patches.enter_context(mock.patch.object(scan.plugin_catalog, "fetch_catalogue", return_value={}))
        for name in ("assistant", "insights", "dashboard_inventory", "datasource_query_cost", "adaptive_logs",
                     "adaptive_traces", "public_dashboards", "alert_routing", "slo_inventory", "synthetic_inventory",
                     "irm_integrations", "irm_alert_groups", "ml_jobs", "reports_inventory", "playlists_inventory",
                     "library_panels_inventory", "cloud_accounts", "faro_apps", "signal_inventory", "pdc_networks"):
            row = next((r for r in (fixture.get(name) or {}).values()
                        if isinstance(r, dict) and r.get("available")), None)
            related = {STACK["slug"]: copy.deepcopy(row)} if row else healthy
            patches.enter_context(mock.patch.object(scan, "gather_" + name, return_value=(related, [])))
        patches.enter_context(mock.patch.object(scan, "gather_service_accounts", return_value=({STACK["slug"]: {"state": scan.sa_src.OK, "accounts": []}}, [])))
        patches.enter_context(mock.patch.object(scan, "gather_capability_adoption", return_value=(fixture["capability_adoption"], [])))
        patches.enter_context(mock.patch.object(scan, "gather_loki_config", return_value=({STACK["slug"]: {"limits": {"available": True}, "change_requests": {"available": True}}}, [])))
        patches.enter_context(mock.patch.object(scan, "load_ratecard", return_value=None))
        patches.enter_context(mock.patch.object(scan.gapstate, "load", return_value={}))
        update = patches.enter_context(mock.patch.object(scan.gapstate, "update", return_value={}))
        patches.enter_context(mock.patch.object(hydrate, "hydrate", side_effect=lambda *a, **kw: real_hydrate(*a, loader=lambda *_: None, **kw)))
        patches.enter_context(mock.patch.object(scan.s3emit, "write_views", side_effect=lambda v, *a, **kw: views.append(copy.deepcopy(v)) or []))
        patches.enter_context(mock.patch.object(scan.s3emit, "write_scan", side_effect=lambda s, **kw: records.append(copy.deepcopy(s)) or []))
        patches.enter_context(mock.patch.object(scan.mimir.RemoteWriter, "push", side_effect=lambda m: metrics.extend(m) or len(m)))
        patches.enter_context(mock.patch.object(scan.loki.LokiWriter, "push", side_effect=lambda e: events.extend(e) or len(e)))
        patches.enter_context(mock.patch.object(scan.findings_mod, "derive", side_effect=lambda v, *a: finding_inputs.append(v) or real_derive(v, *a)))
        patches.enter_context(contextlib.redirect_stdout(stdout))
        patches.enter_context(contextlib.redirect_stderr(stderr))
        args = ["--tier", "t2", "--ignore-lock"]
        output = tmp_path / "diagnostic.json"
        if dry_run:
            args += ["--dry-run", "--out", str(output)]
        if limited:
            args += ["--limit", "1"]
        code = scan.main(args)
        updated = update.call_count
    return {"code": code, "calls": calls, "scans": records, "views": views, "metrics": metrics,
            "events": events, "findings": finding_inputs, "gap_updates": updated,
            "diagnostic": output.read_text() if output.exists() else "",
            "stdout": stdout.getvalue(), "stderr": stderr.getvalue()}


def test_actual_scanner_cli_private_s3_composition_and_public_diagnostic_fences(tmp_path):
    result = exercise_cli(tmp_path)
    assert result["code"] == 0, result["stderr"]
    assert SERVICE in json.dumps(result["scans"][0]["data"]["loki_volume"])
    assert SERVICE in json.dumps(result["views"][0]["loki_volume_top_services"])
    assert "alerting_rule_inventory" in result["views"][0]
    public = [result[k] for k in ("metrics", "events", "findings", "diagnostic", "stdout", "stderr")]
    assert SERVICE not in json.dumps(public)
    assert SECRET not in json.dumps(result)
    assert result["scans"][0]["meta"]["sources"]["rule_inventory"]["healthy"]
    assert result["scans"][0]["meta"]["inputs"]["loki_volume"]["source"] == "own"
    assert result["diagnostic"]


@pytest.mark.parametrize("case", ["disabled", "empty", "partial", "limited"])
def test_actual_cli_negative_controls_refuse_or_disable_publication(tmp_path, case):
    result = exercise_cli(tmp_path, enabled=case != "disabled", empty_estate=case == "empty",
                          failed=("/api/prom/api/v1/alerts",) if case == "partial" else (),
                          dry_run=case == "disabled", limited=case == "limited")
    assert SERVICE not in result["diagnostic"] + result["stdout"] + result["stderr"]
    if case == "disabled":
        assert result["code"] == 0
        assert result["calls"] == []
        assert "loki_volume_top_services" not in result["views"][0]
        assert result["scans"][0]["meta"]["inputs"]["rule_inventory"]["state"] == "disabled"
    else:
        assert result["code"] == (2 if case == "limited" else 1), result["stderr"]
        assert not result["views"] and not result["scans"] and not result["metrics"] and not result["events"]
        assert result["gap_updates"] == 0
        assert "REFUSING all S3, Mimir and Loki writes" in result["stderr"]


def test_dashboard_cli_honors_configured_metric_prefix_and_renders_new_views(tmp_path):
    import subprocess
    env = {**os.environ, "GCINSIGHT_METRIC_PREFIX": "synthetic_prefix",
           "GCINSIGHT_VIEWS_DIR": str(ROOT / "testdata/views")}
    result = subprocess.run([sys.executable, "bin/dashboards.py", "--out", str(tmp_path),
                             "--ds-uid", "synthetic-datasource"], cwd=ROOT, env=env,
                            text=True, capture_output=True, timeout=60)
    assert result.returncode == 0, result.stderr
    usage = json.loads((tmp_path / "gcinsight-usage.json").read_text())
    text = json.dumps(usage)
    for name in ("loki_volume_top_services", "alerting_rule_inventory"):
        assert f"/views/{name}.json" in text
    assert "synthetic_prefix_input_age_seconds" in text
    assert "gcinsight_input_age_seconds" not in text
    assert "unknown" in text and "top100" in text and "not exhaustive" in text


def regenerate():
    """Derive synthetic projections through frozen sources and new views through the existing CLI."""
    import subprocess
    path = ROOT / "tests/fixtures/compose_inputs.json"
    original = path.read_text()
    payload = json.loads(original)
    stacks = [{**STACK, "slug": stack["slug"]} for stack in payload["stacks"] if stack.get("status") != "paused"]
    inputs, _ = inputs_for(stacks)
    for name, value in inputs.items():
        if name in payload:
            assert payload[name] == value
            continue
        end = original.rfind("}")
        field = json.dumps({name: value}, indent=1)[2:-2]
        original = original[:end].rstrip() + ",\n" + field + "\n" + original[end:]
    path.write_text(original)
    # The existing dependency re-derivation uses this real composition fixture.
    from tests.test_hydrate import ViewInputsAreDerivedNotAssumed
    harness = ViewInputsAreDerivedNotAssumed()
    harness.setUpClass()
    names = sorted(hydrate.INPUT_OWNER)
    full = harness._build(names)
    declarations = {}
    for name in inputs:
        view = "loki_volume_top_services" if name == "loki_volume" else "alerting_rule_inventory"
        assert view not in harness._build([])
        matches = [n for n in names if harness._build([n]).get(view) == full[view]]
        assert matches == [name]
        declarations[view] = name
    print(json.dumps(declarations, sort_keys=True))
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        subprocess.run(["python3", "bin/make_local_views.py", "--out", directory], cwd=ROOT, check=True, timeout=60)
        for view in declarations:
            (ROOT / "testdata/views" / (view + ".json")).write_bytes((pathlib.Path(directory) / (view + ".json")).read_bytes())


if __name__ == "__main__":
    regenerate()
