"""D-LOKI23 tenant-YAML contract, reduced from the exact200 robk staff witness.

Witness: /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/telemetry/loki-approved-fields.yaml
Provenance: /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/telemetry/loki-witness.json
Only attribute NAMES and configuration shapes are copied; no log/attribute values.
"""
import json

import pytest

from collector import label_rules
from collector.httpclient import Response
from collector.sources import loki_config
from tests import test_label_inventory as contracts_module
from tests.test_label_inventory import STACK, NOW
from collector.sources import label_inventory as source
from collector.httpclient import ReadOnlyClient

ATTRIBUTES = ["service.name", "service.namespace", "service.instance.id", "deployment.environment",
              "cloud.region", "cloud.availability_zone", "k8s.cluster.name", "k8s.namespace.name",
              "k8s.pod.name", "k8s.container.name", "container.name", "k8s.replicaset.name",
              "k8s.deployment.name", "k8s.statefulset.name", "k8s.daemonset.name", "k8s.cronjob.name",
              "k8s.job.name", "app_id", "app_key", "kind", "deployment.environment.name"]
SERVICES = ["service", "app", "application", "app_name", "name", "app_kubernetes_io_name",
            "container", "container_name", "k8s_container_name", "component", "workload", "job", "k8s_job_name"]
WITNESS = ("otlp_config:\n  resource_attributes:\n    attributes_config:\n    - action: index_label\n"
           "      attributes:\n" + "".join("      - " + name + "\n" for name in ATTRIBUTES)
           + "discover_service_name:\n" + "".join("- " + name + "\n" for name in SERVICES)
           + "discover_log_levels: true\n").encode()


def probe_limits(response, *, bounds=source.Bounds()):
    contracts = contracts_module.SourceContracts()
    contracts.setUp()
    def send(req, timeout):
        if req.full_url.endswith("/config/tenant/v1/limits"):
            contracts.requests.append(req)
            return response
        return contracts.send(req, timeout)
    record = source.probe_stack(ReadOnlyClient(transport=send, deadline=60, max_attempts=1),
                                STACK, "synthetic-cap", now=NOW, rpc_transport=send, bounds=bounds)
    results = {r["rule"]: r for r in label_rules.evaluate({"synthetic": record})["results"]}
    return record, results, contracts.requests


def test_staff_witness_exact_shape_including_indentless_lists():
    parsed = loki_config.labelling_limits(Response(200, WITNESS, ""))
    assert parsed["otlp_config"] == {"resource_attributes": {"attributes_config": [
        {"action": "index_label", "attributes": ATTRIBUTES}]}}
    assert parsed["discover_service_name"] == SERVICES
    assert parsed["discover_log_levels"] is True
    assert "allow_structured_metadata" not in parsed
    assert "volume_enabled" not in parsed


def test_real_source_explicit_positive_only_and_unknown_drilldown():
    record, results, requests = probe_limits(Response(200, WITNESS, ""))
    assert (results["L7"]["result"], results["L7"]["evidence"]["observed"],
            results["L7"]["evidence"]["at_least"]) == ("fail", 2, 1)
    assert (results["L9"]["result"], results["L9"]["reason"]) == ("not_evaluated", "missing_input")
    assert label_rules.CATALOGUE.version == 5
    assert all(name not in json.dumps(record) for name in ("k8s.pod.name", "service.instance.id", "app_key"))
    reads = [r for r in requests if r.full_url.endswith("/config/tenant/v1/limits")]
    assert len(reads) == 1 and reads[0].get_method() == "GET"
    assert reads[0].get_header("Authorization").startswith("Basic ")
    assert not any("limits/applied" in r.full_url for r in requests)


@pytest.mark.parametrize("body", [b"retention_period: 744h\n", b"otlp_config: {}\n",
    b"otlp_config:\n  resource_attributes:\n    attributes_config: []\n",
    WITNESS.replace(b"index_label", b"structured_metadata"),
    WITNESS.replace(b"index_label", b"drop"),
    WITNESS.replace(b"k8s.pod.name", b"safe.pod").replace(b"service.instance.id", b"safe.instance"),
    b"discover_service_name: []\ndiscover_log_levels: false\n",
    WITNESS + b"allow_structured_metadata: true\nvolume_enabled: true\n"])
def test_missing_defaults_or_prerequisites_never_manufacture_a_pass(body):
    _, results, _ = probe_limits(Response(200, body, ""))
    assert results["L7"]["result"] != "pass"
    assert (results["L9"]["result"], results["L9"]["reason"]) == ("not_evaluated", "missing_input")


@pytest.mark.parametrize("body", [WITNESS.replace(b"attributes_config:", b"attributes_config: ["),
    WITNESS.replace(b"discover_log_levels: true", b"discover_log_levels: maybe"),
    WITNESS.replace(b"action: index_label", b"action: arbitrary"),
    WITNESS + b"discover_log_levels: false\n",
    WITNESS.replace(b"resource_attributes:", b"resource_attributes: &anchor"),
    WITNESS.replace(b"- service.name", b"- *alias"),
    WITNESS.replace(b"- service.name", b"- !!str canary"),
    WITNESS.replace(b"discover_service_name:\n- service", b"discover_service_name:\n- nested:\n    canary: true"),
    b"otlp_config:\n  resource_attributes:\n    attributes_config:\n    - action: index_label\n      attributes:\n      - k8s.pod.name\n      action: drop\n",
    b'{"otlp_config":', b"otlp_config:\n\tresource_attributes: {}\n"])
def test_malformed_body_cannot_activate_positive_rule(body):
    with pytest.raises((ValueError, SyntaxError)):
        loki_config.labelling_limits(Response(200, body, ""))
    _, results, _ = probe_limits(Response(200, body, ""))
    assert (results["L7"]["result"], results["L7"]["reason"]) == ("not_evaluated", "missing_input")
    assert results["L7"]["evidence"]["condition"] == "none"


@pytest.mark.parametrize("status", [206, 302, 401, 403, 500])
def test_non_exact200_is_not_a_complete_limits_read(status):
    _, results, _ = probe_limits(Response(status, WITNESS, ""))
    assert (results["L7"]["result"], results["L7"]["reason"]) == ("not_evaluated", "missing_input")


def test_response_cap_is_not_a_values_overflow_finding():
    _, results, _ = probe_limits(Response(200, WITNESS, ""), bounds=source.Bounds(response_bytes=256))
    assert results["L7"]["result"] == "not_evaluated"
    assert results["L7"]["evidence"]["condition"] == "none"


@pytest.mark.parametrize("configs,expected", [
    ([{"action": "drop", "attributes": ["k8s.pod.name"]},
      {"action": "index_label", "attributes": ["k8s.pod.name"]}], "not_evaluated"),
    ([{"action": "index_label", "regex": ".*"},
      {"action": "index_label", "attributes": ["k8s.pod.name"]}], "not_evaluated"),
    ([{"action": "drop", "regex": ".*"},
      {"action": "index_label", "attributes": ["k8s.pod.name"]}], "not_evaluated"),
    ([{"action": "index_label", "attributes": ["k8s.pod.name", "k8s.pod.name"]},
      {"action": "drop", "regex": ".*"}], "fail"),
    ([{"action": "index_label", "attributes": ["k8s_pod_name", "service_instance_id"]}], "not_evaluated"),
])
def test_explicit_first_match_no_regex_execution_no_normalization_guess(configs, expected):
    body = {"otlp_config": {"resource_attributes": {"ignore_defaults": True, "attributes_config": configs}}}
    record, results, _ = probe_limits(Response(200, json.dumps(body).encode(), ""))
    assert results["L7"]["result"] == expected
    assert "k8s.pod.name" not in json.dumps(record)
    if expected == "fail":
        assert results["L7"]["evidence"]["offending_labels"] == 1


@pytest.mark.parametrize("body", [
    b'{"discover_log_levels":true,"discover_log_levels":false}',
    b'{"otlp_config":{"resource_attributes":{"attributes_config":null}}}',
    b'{"otlp_config":{"resource_attributes":{"ignore_defaults":"true"}}}',
    b'{"otlp_config":{"scope_attributes":[]}}',
    b'{"discover_service_name":null}',
    b'{"discover_service_name":[true]}',
    b"discover_service_name:\n" + b"- app\n" * 257,
    b"discover_service_name:\n- " + b"x" * 4097 + b"\n",
    b"discover_service_name: []\n" + b"# comment\n" * 4096,
    b"otlp_config:\n  resource_attributes:\n    attributes_config:\n      nested:\n        nested:\n          nested:\n            nested:\n              nested:\n                nested: true\n",
])
def test_shape_and_complexity_bounds_are_unavailable_not_violations(body):
    with pytest.raises((ValueError, SyntaxError)):
        loki_config.labelling_limits(Response(200, body, ""))
    _, results, _ = probe_limits(Response(200, body, ""))
    assert (results["L7"]["result"], results["L7"]["reason"]) == ("not_evaluated", "missing_input")
    assert results["L7"]["evidence"]["condition"] == "none"


def test_deadline_and_invalid_inventory_never_reach_an_unapproved_host():
    import urllib.parse
    contracts = contracts_module.SourceContracts()
    contracts.setUp()
    clock = [0.0]
    def send(req, timeout):
        if req.full_url.endswith("/config/tenant/v1/limits"):
            clock[0] = 2.0
            return Response(200, WITNESS, "")
        return contracts.send(req, timeout)
    client = ReadOnlyClient(transport=send, deadline=1, max_attempts=1, clock=lambda: clock[0])
    record = source.probe_stack(client, STACK, "synthetic-cap", now=NOW, rpc_transport=send)
    results = {r["rule"]: r for r in label_rules.evaluate({"synthetic": record})["results"]}
    assert (results["L7"]["result"], results["L7"]["reason"]) == ("not_evaluated", "deadline")
    for base in ("http://logs.example.test", "https://user@logs.example.test", "https://logs.example.test/path",
                 "https://logs.example.test?query=1", "https://logs.example.test#fragment"):
        stack = {**STACK, "hlInstanceUrl": base}
        contracts.requests.clear()
        record = source.probe_stack(ReadOnlyClient(transport=contracts.send, deadline=60, max_attempts=1),
                                    stack, "synthetic-cap", now=NOW, rpc_transport=contracts.send)
        assert not any(urllib.parse.urlsplit(r.full_url).hostname == "logs.example.test" for r in contracts.requests)
        assert record["signals"]["logs"]["state"] == "unavailable"


def test_reserves_existing_log_value_slot_and_retention_projection_stays_private():
    record, _, requests = probe_limits(Response(200, WITNESS, ""), bounds=source.Bounds(keys=1))
    log_reads = [r for r in requests if "//logs." in r.full_url]
    assert len(log_reads) == 3  # labels + existing selected series + reserved tenant limits
    assert not any("/label/" in r.full_url for r in log_reads)
    from tests import test_loki_config as retention_contract
    client = retention_contract.Client([retention_contract.Response(200, WITNESS),
                                        retention_contract.Response(200, {"items": []})])
    retention = loki_config.probe_stack(client, retention_contract.STACK, "cap", "reader")
    assert set(retention["limits"]) == {"available", "slug", "state"}
    assert not any(name in json.dumps(retention) for name in ATTRIBUTES)
    assert record["signals"]["logs"]["inputs"]["otlp_churn_labels"]["samples"][0]["value"] == 2


RETENTION_BLOCK = (b"retention_stream:\n  - period: 31d\n    priority: 4\n"
                   b"    selector: '{service=\"api\"}'\n")
RETENTION_POLICY = [{"selector": '{service="api"}', "minimum_period": "30d"}]


def public_retention(body):
    """Exercise the real GET client and public source, with synthetic network edges only."""
    from tests.test_loki_config import STACK as retention_stack
    calls = []
    def send(req, timeout):
        calls.append(req)
        if req.full_url == "https://logs.example/config/tenant/v1/limits":
            return Response(200, body, "")
        assert req.full_url == ("https://alpha.example/api/plugins/grafana-dbcfg-app/resources/v1/"
                                "lokiconfigretentions")
        return Response(200, b'{"items":[]}', "")
    record = loki_config.probe_stack(
        ReadOnlyClient(transport=send, deadline=60, max_attempts=1),
        retention_stack, "synthetic-cap", "synthetic-reader")
    assert len(calls) == 2 and all(req.get_method() == "GET" for req in calls)
    assert calls[0].get_header("Authorization").startswith("Basic ")
    assert calls[1].get_header("Authorization") == "Bearer synthetic-reader"
    return retention_stack, record


def retention_output(stack, record):
    from collector.coverage import Coverage
    from collector.pillars import retention
    return retention.build([stack], Coverage(tier="t2", total=1),
                           {stack["slug"]: record}, expected_policy=RETENTION_POLICY)


@pytest.mark.parametrize("labelling", [
    b"discover_service_name: [service, app]\n",
    b"otlp_config: {resource_attributes: {}}\n",
    b"discover_service_name: &services\n- service\n- app\n",
])
def test_unsupported_labelling_grammar_preserves_public_retention(labelling):
    body = labelling + RETENTION_BLOCK
    stack, record = public_retention(body)
    assert record["limits"]["available"] is True
    assert record["limits"]["retention_stream"] == [
        {"period": "31d", "priority": 4, "selector": '{service="api"}'}]
    metrics, views = retention_output(stack, record)
    assert views["risk_retention_stream"] == [
        {" Stack": stack["slug"], "Period days": 31, "Priority": 4, "Selector": '{service="api"}'}]
    assert views["risk_retention_policy_gaps"] == []
    assert views["risk_retention_policy_status"][0]["Status"] == "compliant"
    values = {name: value for name, _, value in metrics}
    assert values["gcinsight_risk_retention_stacks_measured"] == 1
    assert values["gcinsight_risk_retention_policy_unreadable_stacks"] == 0
    # Refusing the labelling grammar is intentional; this is not a new YAML feature grant.
    with pytest.raises((ValueError, SyntaxError)):
        loki_config.labelling_limits(Response(200, body, ""))
    _, results, _ = probe_limits(Response(200, body, ""))
    assert (results["L7"]["result"], results["L7"]["reason"]) == ("not_evaluated", "missing_input")
    assert (results["L9"]["result"], results["L9"]["reason"]) == ("not_evaluated", "missing_input")
    assert "discover_service_name" not in json.dumps(record)
    assert "otlp_config" not in json.dumps(record)


@pytest.mark.parametrize("prefix", [b"", b"discover_service_name: []\n# unrelated config\n"])
def test_indentless_retention_is_unknown_and_preserves_last_good(prefix, monkeypatch):
    from collector.emit import s3
    stored = {}
    def put(path, key, bucket, dry_run):
        assert bucket == "offline" and not dry_run
        stored[key] = json.loads(path.read_text())
        return key
    monkeypatch.setattr(s3, "_put", put)
    stack, good = public_retention(RETENTION_BLOCK)
    _, good_views = retention_output(stack, good)
    s3.write_views(good_views, {"tier": "t2", "generated_at": "last-good"}, bucket="offline")
    last_good = json.loads(json.dumps(stored))

    indentless = (b"retention_stream:\n# valid YAML, unsupported retention grammar\n"
                  b"- period: 31d\n  priority: 4\n  selector: '{service=\"api\"}'\n")
    stack, record = public_retention(prefix + indentless)
    metrics, views = retention_output(stack, record)
    # The pillar must not publish invented absence or a false below-policy finding.
    assert "risk_retention_stream" not in views
    assert "risk_retention_policy_gaps" not in views
    assert views["risk_retention_policy_status"] == [{
        " Stack": stack["slug"], "Selector": '{service="api"}', "Expected days": 30,
        "Effective days": None, "Status": "unreadable"}]
    values = {name: value for name, _, value in metrics}
    assert "gcinsight_risk_retention_stacks_measured" not in values
    assert "gcinsight_risk_retention_policy_gap_stacks" not in values
    assert "gcinsight_risk_retention_policy_compliant_stacks" not in values
    assert values["gcinsight_risk_retention_policy_unreadable_stacks"] == 1
    assert values["gcinsight_risk_retention_change_request_stacks"] == 1
    assert record["limits"]["available"] is False
    assert record["limits"]["state"] == loki_config.INVALID_RESPONSE
    assert "retention_stream" not in record["limits"]
    assert record["change_requests"]["available"] is True
    s3.write_views(views, {"tier": "t2", "generated_at": "current-unknown"}, bucket="offline")
    for name in ("risk_retention_stream", "risk_retention_policy_gaps"):
        key = f"views/{name}.json"
        assert stored[key] == last_good[key]
    assert stored["views/risk_retention_policy_status.json"]["rows"][0]["Status"] == "unreadable"


def test_real_offline_exporter_and_publication_fences(tmp_path):
    from pathlib import Path
    import subprocess
    import sys
    from collector.pillars import compose, findings
    from collector.coverage import Coverage
    record, _, _ = probe_limits(Response(200, WITNESS, ""))
    metrics, views, _ = compose.build_all([STACK], Coverage(tier="t2", total=1), now=NOW,
                                         label_inventory={STACK["slug"]: record})
    events, _ = findings.derive(views)
    diagnostic = source.diagnostic_scan({"data": {"label_inventory": {STACK["slug"]: record}}, "views": views})
    for name in ("k8s.pod.name", "service.instance.id", "app_key"):
        assert name not in json.dumps([record, metrics, views, events, diagnostic])
    assert not any(s.view.startswith("labelling_") for s in findings.SPECS)
    assert all(len(labels) <= 2 for name, labels, _ in metrics if name.startswith("gcinsight_labelling_"))
    scan, out = tmp_path / "scan.json", tmp_path / "views"
    scan.write_text(json.dumps({"stacks": [STACK], "label_inventory": {STACK["slug"]: record}}))
    run = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "bin/make_local_views.py"),
                          "--scan", str(scan), "--out", str(out)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stderr
    rows = json.loads((out / "labelling_findings.json").read_text())["rows"]
    l7 = next(r for r in rows if r["Rule"] == "L7")
    l9 = next(r for r in rows if r["Rule"] == "L9")
    assert (l7["Result"], l7["Offending objects"], l7["At least"], l7["Catalogue version"]) == ("fail", 2, 1, 5)
    assert (l9["Result"], l9["Reason"]) == ("not_evaluated", "missing_input")
    serialized = run.stdout + run.stderr + "".join(p.read_text() for p in out.glob("*.json"))
    assert all(name not in serialized for name in ("k8s.pod.name", "service.instance.id", "app_key"))
