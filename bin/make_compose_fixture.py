#!/usr/bin/env python3
"""Export compose inputs from deployment S3 scans for later anonymisation.

`tests/test_hydrate.py::ViewInputsAreDerivedNotAssumed` re-derives the per-view input dependency table
by composing every subset of the optional inputs. A live input set is useful when a new branch has no
synthetic coverage yet, but it must never overwrite the committed synthetic fixture.

Trimmed to a sample of stacks so the fixture stays a sensible size, but the sample is chosen to keep
every dependency observable: stacks are only useful here if they appear in the dataplane and detail
maps too, so the sample is drawn from the intersection.

    ./bin/make_compose_fixture.py --output /tmp/compose-inputs-live.json [--stacks N]

The output can contain stack slugs, users, tenant ids and other deployment identifiers. Anonymise it
before deliberately replacing `tests/fixtures/compose_inputs.json`; the exporter refuses that path.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from collector.emit import s3 as s3emit  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMMITTED_FIXTURE = ROOT / "tests" / "fixtures" / "compose_inputs.json"


def output_path(raw: str) -> pathlib.Path:
    """Resolve an explicit export path and protect the committed synthetic fixture."""
    path = pathlib.Path(raw).expanduser().resolve()
    if path == COMMITTED_FIXTURE.resolve():
        raise ValueError(
            "refusing to overwrite tests/fixtures/compose_inputs.json with live identifiers; "
            "export elsewhere and anonymise it first"
        )
    return path


def fetch(tier: str) -> dict:
    uri = f"s3://{s3emit.BUCKET}/scans/{tier}/latest.json"
    proc = subprocess.run(["aws", "s3", "cp", uri, "-", "--region", s3emit.REGION,
                           "--only-show-errors"], capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"cannot read {uri}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stacks", type=int, default=40)
    ap.add_argument("--output", required=True,
                    help="export path outside the committed synthetic fixture")
    args = ap.parse_args(argv)
    try:
        out = output_path(args.output)
    except ValueError as exc:
        ap.error(str(exc))

    t1, t2, t3 = fetch("t1"), fetch("t2"), fetch("t3")
    dataplane = t3["data"]["dataplane"]
    detail = t2["data"]["stack_detail"]
    policies = t1["data"]["access_policies"]
    # Pillar I. T2 gathers it alongside `stack_detail`, so a T2 scan predating PLAN 17E has no such key
    # and the derivation test then cannot exercise the `assistant` dependency at all. Empty rather than
    # absent so the fixture still loads; the test's own subset loop reports the dependency as unproven.
    assistant = t2["data"].get("assistant") or {}
    # Pillar J, same shape and the same caveat: a T2 scan predating it has no such key, and without one
    # the derivation test cannot exercise the `insights` dependency at all.
    insights = t2["data"].get("insights") or {}
    # Stage 19's two S3-only views. Keep empty mappings when the owning T2 has not published them yet;
    # the dependency harness can still distinguish an input-present empty view from an absent view.
    dashboard_inventory = t2["data"].get("dashboard_inventory") or {}
    datasource_query_cost = t2["data"].get("datasource_query_cost") or {}
    # Pillar E's Fleet Management half, moved to T1 (PLAN 18.15). Same caveat as the two above: a T1 scan
    # predating the move has no such key, and the derivation test then cannot exercise the dependency.
    fleet = t1["data"].get("fleet") or {}
    # Stage 19's org-membership input is org-scoped. Keep the complete T1 payload: filtering it by the
    # sampled stack slugs would silently destroy the membership population the fixture must compose.
    raw_org_members = t1["data"].get("org_members")
    org_members = dict(raw_org_members) if isinstance(raw_org_members, Mapping) else {}

    # Only stacks present in BOTH optional maps can demonstrate a dependency on either, so the sample
    # comes from the intersection first, topped up with the rest to keep the inventory-only pillars
    # exercised over a mixed population.
    both = [s for s in t3["data"]["stacks"]
            if str(s["slug"]) in dataplane and str(s["slug"]) in detail]
    rest = [s for s in t3["data"]["stacks"] if s not in both]
    stacks = (both[: args.stacks] + rest[: max(0, args.stacks // 4)])
    slugs = {str(s["slug"]) for s in stacks}

    payload = {
        "_note": "LIVE export from bin/make_compose_fixture.py; anonymise before committing",
        "stacks": stacks,
        "scanned": len(stacks),
        "scannable": len(stacks),
        "dataplane": {k: v for k, v in dataplane.items() if k in slugs},
        "stack_detail": {k: v for k, v in detail.items() if k in slugs},
        "assistant": {k: v for k, v in assistant.items() if k in slugs},
        "insights": {k: v for k, v in insights.items() if k in slugs},
        "dashboard_inventory": {
            k: v for k, v in dashboard_inventory.items() if k in slugs
        },
        "datasource_query_cost": {
            k: v for k, v in datasource_query_cost.items() if k in slugs
        },
        "fleet": {k: v for k, v in fleet.items() if k in slugs},
        "org_members": org_members,
        # Policies are org-scoped rather than per-stack, so they are kept whole but capped.
        "access_policies": policies[:120],
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1, default=str))
    print(f"wrote {out}  -  {len(stacks)} stacks, {len(payload['dataplane'])} dataplane, "
          f"{len(payload['stack_detail'])} detail, {len(payload['assistant'])} assistant, "
          f"{len(payload['insights'])} insights, "
          f"{len(payload['dashboard_inventory'])} dashboard inventories, "
          f"{len(payload['datasource_query_cost'])} datasource-cost records, "
          f"{len(payload['org_members'].get('members', []))} org members, "
          f"{len(payload['access_policies'])} policies")
    if not payload["org_members"]:
        print("WARNING: no `org_members` payload in scans/t1/latest.json  -  the org-membership "
              "dependency cannot be re-derived from this fixture", file=sys.stderr)
    if not payload["insights"]:
        print("WARNING: no `insights` payload in scans/t2/latest.json  -  the Pillar J dependency in "
              "VIEW_INPUTS cannot be re-derived from this fixture", file=sys.stderr)
    if not payload["assistant"]:
        print("WARNING: no `assistant` payload in scans/t2/latest.json  -  the Pillar I dependency in "
              "hydrate.VIEW_INPUTS will NOT be guarded by the derivation test. Run a full T2 first.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
