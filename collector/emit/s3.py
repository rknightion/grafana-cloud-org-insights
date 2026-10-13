"""S3 writer for raw scans and pre-shaped dashboard views.

Two prefixes with different lifecycles and different readers (SPEC §5.3, §8):

- `scans/<tier>/<ts>.json` + `scans/<tier>/latest.json` - the raw envelope. Replay, audit and the input
  T4 diffs against. 90-day lifecycle. **Grafana cannot read this prefix**; the Infinity datasource's IAM
  user is scoped to `views/` only.
- `views/<name>.json` - pre-shaped tables the dashboards render directly. No lifecycle expiry.

Uses the `aws` CLI rather than boto3, to keep the collector dependency-free. The CLI is present in the
container image and on the ECS task.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Mapping

from collector.emit.carry import MAX_FUTURE_SKEW

# Required, with NO default. A hardcoded bucket name means the task writes somewhere its own IAM role
# has no permission for, which surfaces as an AccessDenied that reads like a broken policy and is
# actually a wrong bucket. Terraform creates the bucket and passes the name in, so a deployment always
# knows it; an interactive run has to say which bucket it means.
#
# Read at import: every call site resolves `s3emit.BUCKET` (or takes it as a default), and the lock,
# carry-forward and diff emitters all key off this one value.
BUCKET = os.environ.get("GCINSIGHT_S3_BUCKET", "").strip()
REGION = os.environ.get("GCINSIGHT_S3_REGION", "eu-west-1").strip() or "eu-west-1"


class S3WriteFailed(RuntimeError):
    pass


def _put(local: Path, key: str, bucket: str, dry_run: bool) -> str:
    uri = f"s3://{bucket}/{key}"
    if dry_run:
        return f"DRY-RUN {uri}"
    proc = subprocess.run(
        ["aws", "s3", "cp", str(local), uri, "--region", REGION, "--only-show-errors"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise S3WriteFailed(f"{uri}: {proc.stderr.strip()}")
    return uri


def write_scan(scan: dict[str, Any], *, bucket: str = BUCKET, dry_run: bool = False) -> list[str]:
    """Write the timestamped scan and update `latest.json` for its tier."""
    tier = scan["meta"]["tier"]
    stamp = str(scan["meta"]["generated_at"]).replace(":", "").replace("-", "")
    written: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "scan.json"
        path.write_text(json.dumps(scan, default=str))
        written.append(_put(path, f"scans/{tier}/{stamp}.json", bucket, dry_run))
        written.append(_put(path, f"scans/{tier}/latest.json", bucket, dry_run))
    return written


# Display evidence has its own version; input payload schemas and admission ages do not change.
EVIDENCE_VERSION = 1
# Narrow meanings supported by the existing approved source contracts. Unregistered inputs remain
# unknown. These describe the figures, not universal reader visibility or whole-estate completeness.
SOURCE_SEMANTICS = {
    "loki_volume": "bounded_partial",
    "rule_inventory": "configured_and_current_counts",
    "cloud_accounts": "configured_object_counts",
    "library_panels_inventory": "configured_object_counts",
    "reports_inventory": "configured_object_counts",
    "playlists_inventory": "configured_object_counts",
    "faro_apps": "configured_object_counts",
    "ml_jobs": "configured_object_counts",
    "pdc_networks": "configured_object_counts",
    "irm_integrations": "configured_object_counts",
    "irm_alert_groups": "exact_or_lower_bound_default_window",
    "label_inventory": "bounded_partial",
    "label_risk": "bounded_partial",
    "signal_inventory": "bounded_partial",
}


def _interval(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping) or value.get("clock") != "collector_utc":
        return None
    try:
        start = dt.datetime.fromisoformat(value["started_at"])
        end = dt.datetime.fromisoformat(value["completed_at"])
        if (start.tzinfo is None or end.tzinfo is None or start > end
                or end > dt.datetime.now(dt.timezone.utc) + MAX_FUTURE_SKEW):
            return None
    except (KeyError, ValueError, TypeError, OverflowError):
        return None
    return {"started_at": value["started_at"], "completed_at": value["completed_at"],
            "clock": "collector_utc"}


def inventory_reference(value: Any) -> dict[str, Any] | None:
    """Project recognized minimized fields only; malformed/future evidence is display-unknown."""
    if not isinstance(value, Mapping) or value.get("source") != "gcom_instances":
        return None
    interval = _interval(value.get("observation"))
    members = value.get("members")
    org = value.get("org_id")
    if (interval is None or not isinstance(org, str) or not org.isascii() or not org.isdecimal()
            or len(org) > 32 or not isinstance(members, list) or not 0 < len(members) <= 10000):
        return None
    projected = []
    ids, slugs = set(), set()
    for member in members:
        if not isinstance(member, Mapping):
            return None
        identity, slug, status = member.get("id"), member.get("slug"), member.get("status")
        if (type(identity) is not int or identity <= 0 or identity in ids
                or not isinstance(slug, str) or not slug.strip() or len(slug.encode()) > 512
                or slug in slugs or status not in ("active", "paused", "unknown")):
            return None
        ids.add(identity)
        slugs.add(slug)
        projected.append({"id": identity, "slug": slug, "status": status})
    projected.sort(key=lambda member: member["id"])
    digest = hashlib.sha256(json.dumps(projected, sort_keys=True,
                                      separators=(",", ":")).encode()).hexdigest()
    if digest != value.get("identity_sha256"):
        return None
    response = value.get("response_completeness")
    if response not in ("complete_for_response", "unknown"):
        return None
    return {"source": "gcom_instances", "org_id": org, "identity_sha256": digest,
            "members": projected, "observation": interval, "remote_snapshot_at": None,
            "response_completeness": response, "visibility": "unknown", "authority": "unknown"}


def input_evidence(name: str, *, tier: str | None = None, available: bool | None = None,
                   report: Mapping[str, Any] | None = None,
                   inventory_ref: str | None = None) -> dict[str, Any]:
    """No source times are reconstructed from generated_at/age or payload object timestamps.

    The owned observation seam is inventory only. Other gatherers have no precise interval transport;
    those intervals and source revisions deliberately remain null, even on healthy native inputs.
    """
    report = report or {}
    expected, measured = report.get("expected"), report.get("available")
    valid_counts = (type(expected) is int and type(measured) is int
                    and 0 <= measured <= expected)
    return {
        "owner_tier": tier if tier in ("t1", "t2", "t3", "t4") else None,
        "available": available if type(available) is bool else None,
        "inventory_ref": inventory_ref,
        "observation": None, "source_revision": None,
        "query_window": ({"seconds": 86400, "start": None, "end": None}
                         if name == "loki_volume" else None),
        "completeness": {
            "route_response": "unknown", "visibility": "unknown",
            "semantic": SOURCE_SEMANTICS.get(name, "unknown"),
            "population": {"eligible": expected if valid_counts else None,
                           "measured": measured if valid_counts else None,
                           "excluded": None,
                           "unit": (report.get("unit") if report.get("unit") in
                                    ("stacks", "stack-signals", "org response", "org usage response")
                                    else "stacks")},
        },
    }


def accepted_input_evidence(name: str, value: Any) -> dict[str, Any] | None:
    """Compatible optional owner evidence, tightly projected before crossing the reader boundary.

    It never affects input admission. Unsupported or malformed display metadata is discarded, not
    guessed and not a reason to revive an unavailable input. Unknown source fields never pass through.
    """
    if not isinstance(value, Mapping):
        return None
    tier, available = value.get("owner_tier"), value.get("available")
    ref, revision = value.get("inventory_ref"), value.get("source_revision")
    complete = value.get("completeness")
    if (tier not in ("t1", "t2", "t3", "t4", None)
            or (available is not None and type(available) is not bool)
            or (ref is not None and (not isinstance(ref, str) or not re.fullmatch(r"[0-9a-f]{64}", ref)))
            or (revision is not None and (not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision)))
            or not isinstance(complete, Mapping)):
        return None
    population = complete.get("population")
    if not isinstance(population, Mapping):
        return None
    expected, measured = population.get("eligible"), population.get("measured")
    if ((expected is not None or measured is not None)
            and not (type(expected) is int and type(measured) is int and 0 <= measured <= expected)):
        return None
    result = input_evidence(name, tier=tier, available=available, inventory_ref=ref,
                            report={"expected": expected, "available": measured,
                                    "unit": population.get("unit")})
    # Reject conflicting claimed semantics rather than passing free-form source/error text through.
    if complete != result["completeness"] or value.get("query_window") != result["query_window"]:
        return None
    interval = value.get("observation")
    if interval is not None:
        interval = _interval(interval)
        if interval is None:
            return None
    result.update(observation=interval, source_revision=revision)
    return result


def envelope_evidence(meta: dict[str, Any], data: dict[str, Any], inventory: Any = None) -> dict[str, Any]:
    """Accepted native input metadata, separate from the unchanged input payload schemas."""
    from collector.emit.hydrate import INPUT_OWNER

    ref = inventory_reference(inventory)
    sources = meta.get("sources") or {}
    inputs = {}
    for name in INPUT_OWNER:
        report = sources.get(name) or {}
        if data.get(name) and report.get("healthy") is not False and report.get("state") != "disabled":
            inputs[name] = input_evidence(name, tier=meta.get("tier"), available=True,
                                          report=report,
                                          inventory_ref=ref["identity_sha256"] if ref else None)
    return {"version": EVIDENCE_VERSION, "inventory_ref": ref, "inputs": inputs}


def view_evidence(name: str | None, meta: dict[str, Any]) -> dict[str, Any]:
    from collector.emit.hydrate import INPUT_OWNER, VIEW_INPUTS

    original = meta.get("evidence")
    original = (original if isinstance(original, Mapping)
                and type(original.get("version")) is int
                and original["version"] == EVIDENCE_VERSION else {})
    ref = inventory_reference(original.get("inventory_ref"))
    own = original.get("inputs")
    own = own if isinstance(own, Mapping) else {}
    provenance = meta.get("inputs") or {}
    dependencies = {"inventory": {"observation": ref["observation"] if ref else None,
                                  "completeness": "unknown"}}
    for dependency in sorted(VIEW_INPUTS.get(name, frozenset())):
        entry = provenance.get(dependency) or {}
        # A disabled/unavailable dependency never acquires an old accepted observation. Legacy
        # inputs remain usable under existing hydration rules, but exact evidence stays unknown.
        usable = entry.get("available") is True and not entry.get("stale")
        native = own.get(dependency) if entry.get("source") == "own" else entry.get("evidence")
        detail = accepted_input_evidence(dependency, native) if usable else None
        dependencies[dependency] = detail or input_evidence(
            dependency, tier=INPUT_OWNER[dependency], available=entry.get("available"))
    return {"version": EVIDENCE_VERSION, "inventory_ref": ref,
            "composition_at": meta.get("generated_at"), "dependencies": dependencies,
            "view_scope": {"inventory": "inventory_ref" if ref else None,
                           "row_selection": "unknown"},
            "completeness": "unknown", "storage": None}


def view_stamp(meta: dict[str, Any], *, view: str | None = None) -> dict[str, Any]:
    """The per-view provenance block shared by offline and published envelopes.

    A caller without a registered view cannot claim any optional dependency evidence; inventory
    remains explicit/unknown. Named views use the mechanically derived dependencies.
    """
    return {
        "generated_at": meta.get("generated_at"),
        "tier": meta.get("tier"),
        "stacks_total": meta.get("stacks_total"),
        "stacks_scannable": meta.get("stacks_scannable"),
        "stacks_scanned": meta.get("stacks_scanned"),
        "coverage_ratio": meta.get("coverage_ratio"),
        # Per-input provenance (emit/hydrate.py). A panel showing "Data age" from the scan timestamp
        # alone is misleading once a tier composes from another tier's inputs: the scan is minutes old
        # and the figures in it can be hours old. This is what makes that visible per view.
        "inputs": meta.get("inputs") or {},
        "evidence": view_evidence(view, meta),
    }


def view_payload(rows: list[dict[str, Any]] | dict[str, Any],
                 stamp: dict[str, Any]) -> dict[str, Any]:
    """The published shape of one view.

    Exposed so anything generating views OFFLINE writes the same envelope the collector publishes.
    A second hand-written copy of this shape drifts, and the symptom is `columns_for` raising
    `AttributeError` on a list, which reads as a code bug rather than a format mismatch.
    """
    return {"meta": stamp, "rows": rows}


def write_views(views: dict[str, list[dict[str, Any]] | dict[str, Any]], meta: dict[str, Any],
                *, bucket: str = BUCKET, dry_run: bool = False,
                view_coverage: dict[str, dict[str, Any]] | None = None) -> list[str]:
    """Write pre-shaped dashboard tables.

    Every view carries `generated_at` and the coverage block, so a dashboard can show freshness and
    partial-scan state without a second fetch (SPEC §5.2).
    """
    written: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, rows in views.items():
            view_meta = view_stamp(meta, view=name)
            if view_coverage is not None and name in view_coverage:
                view_meta["rules_coverage"] = view_coverage[name]
            payload = view_payload(rows, view_meta)
            path = Path(tmp) / f"{name}.json"
            path.write_text(json.dumps(payload, default=str))
            written.append(_put(path, f"views/{name}.json", bucket, dry_run))
    return written
