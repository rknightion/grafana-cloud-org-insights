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

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

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


def view_stamp(meta: dict[str, Any]) -> dict[str, Any]:
    """The per-view provenance block."""
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
                *, bucket: str = BUCKET, dry_run: bool = False) -> list[str]:
    """Write pre-shaped dashboard tables.

    Every view carries `generated_at` and the coverage block, so a dashboard can show freshness and
    partial-scan state without a second fetch (SPEC §5.2).
    """
    written: list[str] = []
    stamp = view_stamp(meta)
    with tempfile.TemporaryDirectory() as tmp:
        for name, rows in views.items():
            payload = view_payload(rows, stamp)
            path = Path(tmp) / f"{name}.json"
            path.write_text(json.dumps(payload, default=str))
            written.append(_put(path, f"views/{name}.json", bucket, dry_run))
    return written
