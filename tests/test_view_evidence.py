"""Offline real serialized S3 artifacts: accepted-success evidence, not an outcome observer.

Synthetic identities are discovered by the fake upstream. Only I/O edges are replaced; inventory
validation, runner transport, envelopes, hydration, withholding and S3 JSON serialization are real.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import shutil
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest
import scan
from collector.coverage import Coverage
from collector.emit import budget, hydrate, loki, s3
from collector.httpclient import ReadOnlyClient, Response
from collector.sources import gcom
from tests.test_scan import cfg_for

NOW = dt.datetime(2026, 10, 13, 9, tzinfo=dt.timezone.utc)
PRIVATE = "private-body-error-canary@example.test"
X = {"id": 5000001, "slug": "synthetic-x", "orgId": 1, "status": "active"}
Y = {"id": 5000002, "slug": "synthetic-y", "orgId": 1, "status": "paused"}


def inventory_body(items):
    return {"items": items, "total": len(items), "pages": 1, "page": 1,
            "pageSize": 5000, "links": [], "orderBy": "id", "direction": "asc"}


def client_for(body, status=200):
    def transport(request, timeout):
        assert request.method == "GET"
        assert request.full_url == "https://grafana.com/api/instances?orgId=1"
        return Response(status, json.dumps(body).encode(), request.full_url)
    return ReadOnlyClient(transport=transport, max_attempts=1)


def discover(items):
    return gcom.fetch_inventory(client_for(inventory_body(items)), cfg_for("t3"))


def envelope_for(stacks, *, inputs=None, sources=None, marker=None):
    coverage = Coverage(tier="t3", total=len(stacks))
    for stack in stacks:
        coverage.record_ok(stack["slug"])
    # The compatible list result is the explicit transport; a legacy plain list has no evidence.
    result = scan.envelope(cfg_for("t3"), coverage, {"stacks": stacks, **(inputs or {})},
                           {"sources": sources or {}})
    if marker:
        result["meta"]["generated_at"] = marker
    result["meta"]["inputs"] = {
        name: {"available": True, "source": "own", "tier": "t3", "age_seconds": 0,
               "stale": False, "schema_version": 1}
        for name in inputs or {}
    }
    return result


def store_views(root, views, meta, coverage=None):
    def put(path, key, bucket, dry_run):
        assert not dry_run
        target = root / key
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        s3.write_views(views, meta, bucket="offline", view_coverage=coverage)
    return {key: json.loads((root / key).read_text()) for key in
            ("views/" + name + ".json" for name in views)}


def evidence(payload):
    block = payload["meta"].get("evidence")
    assert block is not None, "accepted artifact needs versioned evidence, not generated_at inference"
    assert block["version"] == 1
    return block


def test_removed_stack_binds_each_exact_object_without_rewriting_history(tmp_path):
    first = envelope_for(discover([X, Y]))
    old = store_views(tmp_path, {"estate": [X, Y]}, first["meta"])["views/estate.json"]
    old_bytes = (tmp_path / "views/estate.json").read_bytes()
    second = envelope_for(discover([Y]))
    new = store_views(tmp_path, {"risk_delete_protection": [Y]}, second["meta"])["views/risk_delete_protection.json"]
    a, b = evidence(old)["inventory_ref"], evidence(new)["inventory_ref"]
    assert a["identity_sha256"] != b["identity_sha256"]
    assert [member["id"] for member in a["members"]] == [X["id"], Y["id"]]
    assert [member["id"] for member in b["members"]] == [Y["id"]]
    assert (tmp_path / "views/estate.json").read_bytes() == old_bytes
    assert old["rows"] == [X, Y]
    # No visibility witness: absence is not promoted to authoritative deletion/current membership.
    assert b["visibility"] == b["authority"] == "unknown"
    assert b["remote_snapshot_at"] is None
    interval = b["observation"]
    assert interval["clock"] == "collector_utc"
    assert dt.datetime.fromisoformat(interval["started_at"]) <= dt.datetime.fromisoformat(interval["completed_at"])


@pytest.mark.parametrize("body,status", [
    (inventory_body([X]), 206), ({"error": PRIVATE}, 200),
    ({**inventory_body([X]), "total": 2, "pages": 2}, 200),
    (inventory_body([X, X]), 200),
    (inventory_body([X, {**Y, "id": X["id"]}]), 200),
    (inventory_body([X, {**Y, "slug": X["slug"]}]), 200),
    (inventory_body([{**X, "orgId": 2}]), 200),
    (inventory_body([{**X, "id": True}]), 200),
    (inventory_body([{**X, "slug": ""}]), 200),
    ({**inventory_body([X]), "links": [{"rel": "next", "href": PRIVATE}]}, 200),
    ({**inventory_body([X]), "page": True}, 200),
])
def test_failed_inventory_cannot_create_new_artifact(body, status, tmp_path):
    good = envelope_for(discover([Y]))
    store_views(tmp_path, {"estate": [Y]}, good["meta"])
    original = (tmp_path / "views/estate.json").read_bytes()
    with pytest.raises(RuntimeError) as error:
        gcom.fetch_inventory(client_for(body, status), cfg_for("t3"))
    assert PRIVATE not in str(error.value)
    assert (tmp_path / "views/estate.json").read_bytes() == original


def test_legacy_missing_metadata_keeps_rows_and_marks_exact_times_unknown(tmp_path):
    marker = "2026-10-12T08:00:00+00:00"
    meta = {"generated_at": marker, "tier": "t1", "coverage_ratio": 1.0,
            "inputs": {"dataplane": {"available": True, "age_seconds": 3600}}}
    payload = store_views(tmp_path, {"cost": [{"Stack": X["slug"]}]}, meta)["views/cost.json"]
    block = evidence(payload)
    assert payload["rows"] == [{"Stack": X["slug"]}]
    assert payload["meta"]["generated_at"] == block["composition_at"] == marker
    assert payload["meta"]["inputs"] == meta["inputs"]
    assert block["inventory_ref"] is None
    assert block["storage"] is None
    assert block["dependencies"]["dataplane"]["observation"] is None
    assert block["dependencies"]["dataplane"]["completeness"]["semantic"] == "unknown"
    assert set(block["dependencies"]) == {"inventory", "dataplane"}


def test_retained_last_good_survives_rejected_and_future_hydration(tmp_path):
    good = envelope_for(discover([X]), inputs={"dataplane": {"synthetic-x": {"series": 42}}})
    good["meta"]["generated_at"] = NOW.isoformat()
    store_views(tmp_path, {"cost": [{"Stack": X["slug"], "Series": 42}]}, good["meta"])
    before = (tmp_path / "views/cost.json").read_bytes()
    evidence(json.loads(before))
    for rejection in ("future", "source"):
        owner = json.loads(json.dumps(good))
        if rejection == "future":
            owner["meta"]["generated_at"] = (NOW + hydrate.MAX_FUTURE_SKEW + dt.timedelta(seconds=1)).isoformat()
        else:
            owner["meta"]["sources"]["dataplane"] = {"healthy": False, "available": 0, "expected": 1}
        _, prov = hydrate.hydrate("t1", {}, now=NOW, loader=lambda tier, bucket: owner if tier == "t3" else None)
        views, withheld = hydrate.filter_views({"cost": [], "estate": [Y]}, prov)
        assert "cost" in withheld and "cost" not in views
        other = envelope_for(discover([Y]))
        other["meta"]["inputs"] = prov
        store_views(tmp_path, views, other["meta"])
        assert (tmp_path / "views/cost.json").read_bytes() == before
        assert not prov.satisfied("dataplane")
        assert "evidence" not in prov["dataplane"]


def test_dependencies_are_derived_rules_coverage_and_old_consumers_unchanged(tmp_path):
    owner = envelope_for(discover([X]), inputs={"dataplane": {"x": 1}, "assistant": {"x": 1}})
    rules = {"cost": {"evaluated": 1, "passed": 1}}
    payload = store_views(tmp_path, {"cost": []}, owner["meta"], rules)["views/cost.json"]
    block = evidence(payload)
    assert set(block["dependencies"]) == {"inventory", *hydrate.VIEW_INPUTS["cost"]}
    assert "assistant" not in block["dependencies"]
    assert payload["meta"]["rules_coverage"] == rules["cost"]
    assert payload["meta"]["inputs"] == owner["meta"]["inputs"]
    assert payload["rows"] == []
    assert block["completeness"] == "unknown", "zero findings/rule pass/floor pass is not exhaustiveness"
    assert sum(spec.series for spec in budget.CATALOGUE) == 13827
    assert len(hydrate.INPUT_OWNER) == budget.INPUT == 32


def test_original_optional_evidence_survives_accepted_hydration_only(tmp_path):
    owner = envelope_for(discover([X]), inputs={"dataplane": {"synthetic-x": {"series": 42}}})
    owner["meta"]["generated_at"] = (NOW - dt.timedelta(hours=2)).isoformat()
    native = owner["meta"]["evidence"]["inputs"]["dataplane"]
    native["observation"] = {"started_at": (NOW - dt.timedelta(hours=3)).isoformat(),
                             "completed_at": (NOW - dt.timedelta(hours=2)).isoformat(),
                             "clock": "collector_utc"}
    native["source_revision"] = "a" * 40
    # Round-trip the real owner artifact serialization, not a hand-built consumer proxy.
    captured = {}
    def put(path, key, bucket, dry_run):
        captured[key] = json.loads(path.read_text())
        return key
    with mock.patch.object(s3, "_put", side_effect=put):
        s3.write_scan(owner, bucket="offline")
    original = captured["scans/t3/latest.json"]
    _, prov = hydrate.hydrate("t1", {}, now=NOW, loader=lambda tier, bucket: original if tier == "t3" else None)
    assert prov["dataplane"].get("evidence") == original["meta"]["evidence"]["inputs"]["dataplane"]
    new_meta = envelope_for(discover([Y]))["meta"]
    new_meta["inputs"] = prov
    result = store_views(tmp_path, {"cost": []}, new_meta)["views/cost.json"]
    assert evidence(result)["dependencies"]["dataplane"] == prov["dataplane"]["evidence"]
    # Old producer to new consumer: eligibility/age unchanged; unsupported evidence never guessed.
    for optional in (None, {"version": 99, "inputs": {"dataplane": {"observation": PRIVATE}}}):
        legacy = json.loads(json.dumps(original))
        legacy["meta"]["evidence"] = optional
        _, old_prov = hydrate.hydrate("t1", {}, now=NOW, loader=lambda tier, bucket: legacy if tier == "t3" else None)
        assert old_prov.satisfied("dataplane")
        assert old_prov["dataplane"]["age_seconds"] == 7200
        assert "evidence" not in old_prov["dataplane"]
    malformed = json.loads(json.dumps(original))
    malformed["meta"]["evidence"]["inputs"]["dataplane"]["observation"]["completed_at"] = "2999-01-01T00:00:00+00:00"
    _, accepted = hydrate.hydrate("t1", {}, now=NOW, loader=lambda tier, bucket: malformed if tier == "t3" else None)
    assert accepted.satisfied("dataplane") and "evidence" not in accepted["dataplane"]
    # Own-input prohibition remains stronger than optional historical evidence.
    _, own = hydrate.hydrate("t3", {}, now=NOW, loader=lambda tier, bucket: original)
    assert not own.satisfied("dataplane") and "evidence" not in own["dataplane"]


def test_source_specific_bounds_do_not_copy_private_payloads(tmp_path):
    payloads = {
        "loki_volume": {"synthetic-x": {"state": "complete", "services": [{"service": PRIVATE, "bytes": 7}], "total_bytes": None, "other_bytes": None}},
        "rule_inventory": {"synthetic-x": {"state": "partial", "mimir_rules": 1, "loki_rules": None}},
        "cloud_accounts": {"synthetic-x": {"available": True, "account_count": 0}},
        "label_inventory": {"private_register": PRIVATE},
    }
    sources = {name: {"healthy": True, "available": 9, "expected": 10} for name in payloads}
    owner = envelope_for(discover([X]), inputs=payloads, sources=sources)
    owner["meta"]["inputs"] = {name: {"available": True, "source": "own", "tier": "t2"} for name in payloads}
    artifacts = store_views(tmp_path, {"loki_volume_top_services": [], "alerting_rule_inventory": [], "cloud_accounts": []}, owner["meta"])
    loki = evidence(artifacts["views/loki_volume_top_services.json"])["dependencies"]["loki_volume"]
    assert loki["completeness"]["semantic"] == "bounded_partial"
    assert loki["query_window"] == {"seconds": 86400, "start": None, "end": None}
    assert loki["completeness"]["population"] == {"eligible": 10, "measured": 9, "excluded": None, "unit": "stacks"}
    rules = evidence(artifacts["views/alerting_rule_inventory.json"])["dependencies"]["rule_inventory"]
    assert rules["completeness"]["semantic"] == "configured_and_current_counts"
    aws = evidence(artifacts["views/cloud_accounts.json"])["dependencies"]["cloud_accounts"]
    assert aws["completeness"]["semantic"] == "configured_object_counts"
    assert aws["completeness"]["visibility"] == "unknown"
    assert PRIVATE not in json.dumps(artifacts)


def test_real_t3_runner_transports_fresh_inventory_not_source_object_timestamps(tmp_path):
    upstream = inventory_body([{**X, "createdAt": "2000-01-01T00:00:00Z", "updatedAt": "2001-01-01T00:00:00Z", "description": PRIVATE}])
    with (mock.patch.object(scan.dataplane, "probe_all", return_value={}),
          mock.patch.object(hydrate, "_load_latest", return_value=None),
          mock.patch.object(hydrate.subprocess, "run", return_value=SimpleNamespace(returncode=1)),
          mock.patch.object(scan, "load_ratecard", return_value=None),
          mock.patch.object(scan, "assistant_gaps", return_value={})):
        result = scan.run_t3(client_for(upstream), cfg_for("t3"))
    views, _ = hydrate.filter_views(result["_emit"]["views"], result["meta"]["inputs"])
    artifacts = store_views(tmp_path, views, result["meta"])
    assert artifacts
    for artifact in artifacts.values():
        inv = evidence(artifact)["inventory_ref"]
        assert inv["org_id"] == "1"
        assert dt.datetime.fromisoformat(inv["observation"]["started_at"]).year > 2001
        assert PRIVATE not in json.dumps(artifact["meta"]["evidence"])
        assert inv["response_completeness"] == "complete_for_response"


@pytest.mark.parametrize("boundary", ["loki", "diagnostic"])
def test_common_publication_strips_only_new_private_evidence_at_real_boundaries(boundary, tmp_path):
    owner = envelope_for(discover([X]), inputs={"dataplane": {"synthetic-x": {"series": 42}}})
    owner["meta"]["tier"] = "t1"
    owner["meta"]["evidence"]["privacy_canary"] = "native-private-evidence-only"
    original = s3.input_evidence("dataplane", tier="t3", available=True)
    owner["meta"]["inputs"]["dataplane"].update(
        source="hydrated", evidence={**original, "privacy_canary": "hydrated-private-evidence-only"},
        legacy_notice="existing-provenance-preserved")
    owner["_emit"] = {"metrics": [], "views": {"cost": []}, "view_coverage": {}}
    captured, wire = {}, []
    def put(path, key, bucket, dry_run):
        captured[key] = json.loads(path.read_text())
        return key
    class Ack:
        status = 204
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
    def post(request, timeout):
        assert request.method == "POST" and request.full_url == "https://loki.invalid/loki/api/v1/push"
        wire.append(json.loads(request.data))
        return Ack()
    real_payload = loki.build_payload
    def payload(entries, **kwargs):
        result = real_payload(entries, **kwargs)
        if boundary == "diagnostic":
            wire.append(result)
        return result
    output, stdout, stderr = tmp_path / "diagnostic.json", io.StringIO(), io.StringIO()
    cfg = replace(cfg_for("t1"), dry_run=boundary == "diagnostic")
    with (mock.patch.object(scan.config, "load", return_value=cfg),
          mock.patch.object(scan, "_verified_ecs_runtime", return_value=True),
          mock.patch.object(scan, "run_t1", return_value=owner),
          mock.patch.object(s3, "_put", side_effect=put),
          mock.patch.object(scan.mimir.RemoteWriter, "push", return_value=0),
          mock.patch.object(loki, "build_payload", side_effect=payload),
          mock.patch.object(scan.scanlock.ScanLock, "acquire", return_value=None),
          mock.patch.object(scan.scanlock.ScanLock, "release", return_value=None),
          mock.patch("subprocess.run", side_effect=AssertionError("no external command")),
          mock.patch("urllib.request.urlopen", side_effect=post),
          contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr)):
        args = ["--tier", "t1"] + (["--dry-run", "--out", str(output)] if cfg.dry_run else [])
        assert scan.main(args) == 0
    assert wire, "proof must observe native Loki serialization, not a summary helper proxy"
    native = "native-private-evidence-only"
    hydrated = "hydrated-private-evidence-only"
    digest = owner["meta"]["evidence"]["inventory_ref"]["identity_sha256"]
    private = captured["scans/t1/latest.json"]
    assert native in json.dumps(private) and hydrated in json.dumps(private)
    assert captured["views/cost.json"]["meta"]["evidence"]["inventory_ref"]["identity_sha256"] == digest
    summaries = [json.loads(line) for stream in wire[-1]["streams"]
                 if stream["stream"]["event"] == "scan_summary" for _, line in stream["values"]]
    assert len(summaries) == 1
    expected = json.loads(json.dumps(owner["meta"]))
    expected.pop("evidence")
    expected["inputs"]["dataplane"].pop("evidence")
    if cfg.dry_run:
        diagnostic = json.loads(output.read_text())
        assert diagnostic["meta"] == expected, "--out must retain old fields but no new evidence"
    assert summaries[0] == {**expected, "level": "info"}, "Loki must retain old fields but no new evidence"
    for surface in (json.dumps(wire), output.read_text() if output.exists() else "", stdout.getvalue(), stderr.getvalue()):
        assert native not in surface and hydrated not in surface and digest not in surface
    # Publication projections must not mutate the private original or downstream S3 artifacts.
    assert "evidence" in owner["meta"] and "evidence" in owner["meta"]["inputs"]["dataplane"]


@pytest.mark.parametrize("state", ["removed-stack", "failed-inventory", "missing-metadata", "retained-last-good"])
def test_section7_real_objects_through_public_dashboard_cli(state, tmp_path):
    root = Path(__file__).resolve().parent.parent
    shutil.copytree(root / "testdata" / "views", tmp_path / "views")
    name = "cost_cardinality_outliers"
    rows = json.loads((tmp_path / "views" / (name + ".json")).read_text())["rows"][:1]
    rows[0][" Stack"] = X["slug"]
    owner = envelope_for(discover([X, Y]), inputs={"dataplane": {"synthetic-x": {"series": 42}}},
                         marker=NOW.isoformat())
    owner["meta"]["inputs"]["dataplane"]["age_seconds"] = 7200
    artifacts = store_views(tmp_path, {name: rows}, owner["meta"])
    artifact = artifacts["views/" + name + ".json"]
    # This assertion is deliberately about a real emitted object; old code fails here before any
    # unchanged conservative consumer is used as a weaker proxy for the additive contract.
    original_ref = evidence(artifact)["inventory_ref"]
    path = tmp_path / "views" / (name + ".json")
    before = path.read_bytes()
    later = envelope_for(discover([Y]), marker=(NOW + dt.timedelta(hours=1)).isoformat())
    estate_rows = json.loads((tmp_path / "views" / "estate.json").read_text())["rows"][:1]
    estate_rows[0][" Stack"] = Y["slug"]
    if state == "removed-stack":
        store_views(tmp_path, {"estate": estate_rows}, later["meta"])
        assert original_ref["identity_sha256"] != later["meta"]["evidence"]["inventory_ref"]["identity_sha256"]
    elif state == "failed-inventory":
        with pytest.raises(RuntimeError):
            gcom.fetch_inventory(client_for(inventory_body([Y]), 206), cfg_for("t3"))
    elif state == "missing-metadata":
        # An actual legacy artifact, not a new evidence block with guessed historical times.
        artifact["meta"].pop("evidence")
        artifact["meta"]["inputs"] = {}
        path.write_text(json.dumps(artifact))
    else:
        _, prov = hydrate.hydrate("t1", {}, now=NOW, loader=lambda *_: None)
        views, withheld = hydrate.filter_views({name: [], "estate": estate_rows}, prov)
        assert name in withheld
        store_views(tmp_path, views, later["meta"])
    if state != "missing-metadata":
        assert path.read_bytes() == before
    env = {key: value for key, value in os.environ.items() if not key.startswith("GCINSIGHT_")}
    env.update(GCINSIGHT_VIEWS_DIR=str(tmp_path / "views"), GCINSIGHT_S3_BUCKET="synthetic-evidence",
               GCINSIGHT_DASHBOARD_UID_PREFIX="evidence", GCINSIGHT_GRAFANA_TOKEN="")
    cli = subprocess.run([sys.executable, str(root / "bin" / "dashboards.py"),
                          "--out", str(tmp_path / "built"), "--ds-uid", "synthetic-infinity"],
                         cwd=root, env=env, capture_output=True, text=True, timeout=90)
    assert cli.returncode == 0, cli.stderr
    assembled = json.loads((tmp_path / "built" / "evidence-cost.json").read_text())
    elements = assembled["spec"]["elements"]
    assert elements["cardinality"]["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]["root_selector"] == "rows"
    metadata = elements["_meta_" + name]["spec"]["data"]["spec"]["queries"][0]["spec"]["query"]["spec"]
    assert metadata["url"].endswith("/views/" + name + ".json")
    assert "$millis()" in metadata["root_selector"]
    assert X["slug"] not in json.dumps(assembled), "no private roster embedded in the dashboard JSON"
    retained = os.environ.get("GCINSIGHT_VIEW_EVIDENCE_ARTIFACTS")
    if retained:
        shutil.copytree(tmp_path, Path(retained) / state, dirs_exist_ok=True)
        (Path(retained) / state / "cli.log").write_text(cli.stdout + cli.stderr)
