#!/usr/bin/env python3
"""What this platform costs to run, computed from measured volumes (SPEC §11.5).

    python3 bin/cost_model.py            # uses the committed evidence fixtures
    python3 bin/cost_model.py --scan /tmp/t3.json

**The headline: the T3 read sweep costs nothing.** It does not, for three separate
reasons, each verified rather than assumed:

1. **T3 issues no PromQL.** Every call is metadata or control plane - the Mimir *cardinality* API,
   Adaptive Metrics `/aggregations/*`, and Fleet Management's Connect-RPC list methods. There is no
   `/api/v1/query` and no `query_range` anywhere in `sources/dataplane.py`.
2. **Grafana Cloud does not bill metrics queries.** Confirmed against grafana.com/pricing: metrics are
   billed on active series, and "queries are not separately billed for metrics".
3. **Loki query cost applies only beyond a fair-use ratio, and the collector makes zero Loki queries.**
   It only writes. Humans reading the dashboards will query, but that is a handful of requests.

So the cost is entirely on the **write** side, and it is small and precisely known.

Rates are Grafana Cloud **Pro list price**, which is an upper bound: a large estate is typically on the
`advanced` plan, a committed enterprise contract whose effective rates are lower and are not ours to
assume. Treat every currency figure here as a ceiling, and say so when quoting it.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collector.coverage import Coverage
from collector.emit import carry, loki, mimir
from collector.pillars import compose
from collector.sources.gcom import user_record

TESTDATA = pathlib.Path(__file__).resolve().parent.parent / "testdata"

# Grafana Cloud Pro list price, fetched from grafana.com/pricing on 2026-08-17.
METRICS_PER_1K_SERIES = 6.50   # $/1k active series/month. Queries NOT billed.
LOGS_WRITE_PER_GB = 0.400      # $/GB ingested
LOGS_PROCESS_PER_GB = 0.050    # $/GB
LOGS_RETAIN_PER_GB = 0.100     # $/GB retained

# Tier cadences from SPEC §5.2.
RUNS_PER_MONTH = {"t1": 730.0, "t2": 30.4, "t3": 121.7, "t4": 30.4}

NOW = dt.datetime(2026, 8, 17, 20, 0, tzinfo=dt.timezone.utc)


def _coverage(stacks, tier):
    coverage = Coverage(tier=tier, total=len(stacks))
    for stack in stacks:
        if stack.get("status") == "paused":
            coverage.record_skipped(str(stack["slug"]), "paused")
        else:
            coverage.record_ok(str(stack["slug"]))
    return coverage


def line_bytes(entries) -> int:
    """Loki bills UNCOMPRESSED ingested line bytes, not the JSON envelope around them."""
    payload = loki.build_payload(entries, timestamp=NOW)
    return sum(len(value[1].encode()) for stream in payload["streams"] for value in stream["values"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", help="a real T3 scan envelope; defaults to the evidence fixtures")
    ap.add_argument(
        "--write-stack",
        default=os.environ.get("GCINSIGHT_WRITE_STACK", ""),
        help="write-stack slug for the local footprint denominator; defaults to GCINSIGHT_WRITE_STACK",
    )
    args = ap.parse_args()

    if args.scan:
        envelope = json.loads(pathlib.Path(args.scan).read_text())
        stacks = envelope["data"]["stacks"]
        dataplane = envelope["data"].get("dataplane") or {}
    else:
        stacks = json.loads((TESTDATA / "gcom-instances-2026-08-17.json").read_text())["items"]
        dataplane = json.loads((TESTDATA / "t3-dataplane-2026-08-17.json").read_text())

    users = json.loads((TESTDATA / "gcom-instance-users.json").read_text())["items"]
    # T2 detail for the whole estate, extrapolated from the one real sample. The sampled stack has 12
    # users and 24 service accounts, which is at the heavier end, so this over-estimates.
    sample = {
        "users": [user_record(u) for u in users],
        "service_accounts": [
            {"name": f"sa{i}", "kind": "custom" if i < 5 else "extsvc", "role": "Viewer",
             "tokens": 1, "isDisabled": False}
            for i in range(24)
        ],
        "plugins": [{"pluginSlug": "p", "version": "1.0.0", "latestVersion": "1.0.1"}],
    }
    detail = {str(s["slug"]): dict(sample, slug=str(s["slug"])) for s in stacks}

    # --- Mimir: active series is the billed unit. Peak = T1 plus everything it carries forward. ---
    t3_metrics, _ = compose.build_all(stacks, _coverage(stacks, "t3"), dataplane=dataplane)
    t1_metrics, _ = compose.build_all(stacks, _coverage(stacks, "t1"))
    state = {"generated_at": NOW.isoformat(), "tier": "t3",
             "metrics": [[n, dict(l), v] for n, l, v in t3_metrics]}
    extra, report = carry.carry_forward(t1_metrics, state, now=NOW + dt.timedelta(hours=1))
    series = len(t1_metrics) + len(extra) + len(carry.report_metrics(report, "t1"))

    # --- Loki: uncompressed ingested bytes per run, times the cadence. ---
    per_run = {
        "t1": line_bytes([loki.summary_event("t1", {})] + loki.stack_detail_events("t1", stacks)),
        "t2": line_bytes([loki.summary_event("t2", {})] + loki.stack_identity_events("t2", detail)),
        "t3": line_bytes([loki.summary_event("t3", {})]
                         + loki.stack_detail_events("t3", stacks, dataplane)),
        "t4": line_bytes([loki.summary_event("t4", {})]),
    }
    gb_per_month = {t: per_run[t] * RUNS_PER_MONTH[t] / 1e9 for t in per_run}
    total_gb = sum(gb_per_month.values())

    org_series = sum(s.get("hmInstancePromCurrentActiveSeries") or 0 for s in stacks)
    target = [s for s in stacks if str(s["slug"]) == args.write_stack]
    target_series = (target[0].get("hmInstancePromCurrentActiveSeries") or 0) if target else 0

    metrics_cost = series / 1000 * METRICS_PER_1K_SERIES
    logs_cost = total_gb * (LOGS_WRITE_PER_GB + LOGS_PROCESS_PER_GB + LOGS_RETAIN_PER_GB)

    print("READ SIDE - the T3 sweep")
    print("  API reads per 6-hourly run: derive from the scan envelope")
    print("  PromQL queries issued:                       0")
    print("  Metrics queries billed by Grafana Cloud:     never (billed on active series)")
    print("  Loki queries issued by the collector:        0")
    print("  => READ COST: $0.00/month\n")

    print("WRITE SIDE - Mimir")
    print(f"  active series (peak, T1 incl. carry-forward): {series:,}")
    if target_series:
        print(f"  as a share of {args.write_stack}'s own {target_series:,}:"
              f"   +{100*series/target_series:.1f}%")
    else:
        print("  write-stack share: not computed; pass --write-stack or set GCINSIGHT_WRITE_STACK")
    print(f"  as a share of the org's {org_series:,}:      +{100*series/org_series:.3f}%")
    print(f"  at ${METRICS_PER_1K_SERIES}/1k series/month:                  ${metrics_cost:.2f}/month\n")

    print("WRITE SIDE - Loki (uncompressed ingest)")
    print(f"  {'tier':6}{'bytes/run':>14}{'runs/mo':>10}{'GB/month':>12}")
    for tier in ("t1", "t2", "t3", "t4"):
        print(f"  {tier:6}{per_run[tier]:>14,}{RUNS_PER_MONTH[tier]:>10}{gb_per_month[tier]:>12.4f}")
    print(f"  {'TOTAL':6}{'':>14}{'':>10}{total_gb:>12.4f} GB/month")
    print(f"  at ${LOGS_WRITE_PER_GB}+${LOGS_PROCESS_PER_GB}+${LOGS_RETAIN_PER_GB}/GB:"
          f"                    ${logs_cost:.2f}/month")
    print(f"  (Pro includes 50 GB/month; this is {100*total_gb/50:.2f}% of that allowance)\n")

    print(f"TOTAL, Pro LIST price (an upper bound):        ${metrics_cost + logs_cost:.2f}/month")
    print(f"                                              ${(metrics_cost + logs_cost)*12:.2f}/year")
    print("  A committed contract runs at lower, unknown rates. This is a CEILING, not a price.\n")

    # --- Proportionality: declared reductions from verbose Adaptive recommendations. ---
    measured = [
        (dataplane.get(str(s["slug"])) or {}).get("adaptive_metrics") or {}
        for s in stacks
    ]
    remediable = sum(am.get("remediable_series") or 0 for am in measured if am.get("available"))
    print("PROPORTIONALITY - arithmetic, not a contracted saving")
    print(f"  remediable series declared by verbose Adaptive recommendations:     {remediable:,}")
    if remediable:
        print(f"  the platform's own footprint as a share of that:                    "
              f"{100*series/remediable:.4f}%")
        print(f"  remediable volume at the same list rate:                            "
              f"${remediable/1000*METRICS_PER_1K_SERIES:,.0f}/month")
        print(f"  ratio, platform cost : remediable volume:                           "
              f"1 : {remediable/series:,.0f}")
    else:
        print("  no verbose reduction totals in this input; no savings value is inferred")
    print("  This standalone ceiling uses base-series list pricing; contract currency and DPM-aware "
          "savings come only from the optional rate card and live dashboard inputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
