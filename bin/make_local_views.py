#!/usr/bin/env python3
"""Compose every dashboard view from a local scan fixture and write them to a directory.

Point `GCINSIGHT_VIEWS_DIR` at the output and `bin/dashboards.py` will build against it: no AWS
credentials, no deployed bucket, no live estate. That is how the test suite runs, and it is the
quickest way to see what a dashboard looks like before anything is provisioned.

    ./bin/make_local_views.py                                  # fixture -> testdata/views/
    ./bin/make_local_views.py --scan scans/t3/latest.json       # a real scan envelope instead

The envelope comes from `emit.s3.view_payload`, the same function the collector publishes with, so a
column spec derived here is the one a panel will really see.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collector.coverage import Coverage          # noqa: E402
from collector.emit import diff as diffmod        # noqa: E402
from collector.emit import hydrate                # noqa: E402
from collector.emit import s3 as s3emit          # noqa: E402
from collector.pillars import compose            # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_IN = ROOT / "tests" / "fixtures" / "compose_inputs.json"
DEFAULT_OUT = ROOT / "testdata" / "views"


def _coverage(stacks: list[dict], tier: str) -> Coverage:
    """Rebuild coverage from the fixture the same way a scan would.

    Paused stacks are SKIPPED, not failed: counting them as failures caps the ratio below 100% for
    ever and trains everyone to ignore the warning.
    """
    cov = Coverage(tier=tier, total=len(stacks))
    for s in stacks:
        slug = str(s.get("slug"))
        if str(s.get("status", "")).lower() == "paused":
            cov.record_skipped(slug, "paused")
        else:
            cov.record_ok(slug)
    return cov


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", type=pathlib.Path, default=DEFAULT_IN,
                    help=f"input: a compose fixture or a scan envelope (default {DEFAULT_IN})")
    ap.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT,
                    help=f"output directory (default {DEFAULT_OUT})")
    ap.add_argument("--tier", default="t3",
                    help="tier recorded in each view's provenance block (default t3)")
    args = ap.parse_args(argv)

    doc = json.loads(args.scan.read_text())
    # A scan envelope nests its inputs under `data`; a fixture holds them at the top level.
    src = doc.get("data", doc)
    stacks = src.get("stacks")
    if not stacks:
        print(f"error: {args.scan} carries no `stacks` - nothing to compose from", file=sys.stderr)
        return 2

    cov = _coverage(stacks, args.tier)
    optional_inputs = {name: src.get(name) for name in hydrate.INPUT_OWNER}
    metrics, views = compose.build_all(stacks, cov, **optional_inputs)

    stamp = s3emit.view_stamp({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "tier": args.tier,
        "stacks_total": cov.total,
        "stacks_scannable": cov.scannable,
        "stacks_scanned": cov.scanned,
        "coverage_ratio": cov.ratio,
        "inputs": {k: {"source": "local", "age_seconds": 0.0}
                   for k in hydrate.INPUT_OWNER if src.get(k)},
    })

    # The T4 estate diff is not a pillar - `emit/diff.py` owns it and only T4 runs it, so
    # `compose.build_all` never produces it. Without these two the dashboard build fails on the
    # estate "Change" tab, which is the exact defect of a diff that nothing renders, inverted.
    #
    # The baseline is the same scan with its last two stacks removed, so every tracked figure shows
    # real movement rather than a wall of zeros. It simulates "two stacks were added since then".
    latest_scan = {"data": src}
    baseline_scan = {"data": dict(src, stacks=stacks[:-2])} if len(stacks) > 2 else latest_scan
    now = dt.datetime.now(dt.timezone.utc)
    for window in diffmod.WINDOWS:
        report = diffmod.diff(latest_scan, baseline_scan, now, now - window.target, window=window)
        views[window.view] = diffmod.as_view(report)

    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in sorted(views.items()):
        (args.out / f"{name}.json").write_text(
            json.dumps(s3emit.view_payload(rows, stamp), indent=2, default=str) + "\n"
        )

    print(f"{len(views)} views -> {args.out}   ({len(metrics)} metrics composed, "
          f"coverage {cov.scanned}/{cov.scannable})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
