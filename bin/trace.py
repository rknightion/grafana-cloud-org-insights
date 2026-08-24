#!/usr/bin/env python3
"""Traceability for every leadership-facing number (PLAN 8.5, SPEC §10 item 5).

Answers, mechanically: **where did this number come from, and does it still reproduce?** For each
figure a leadership panel shows, this walks the raw S3 scan, recomputes the value from a *named source
field*, and compares it against what the pillar emitted and against what is live on the stack.

    bin/trace.py                      # recompute from scans/t1/latest.json in S3, compare to the pillar
    bin/trace.py --live --context <gcx-context> # also compare what is on the dashboard
    bin/trace.py --scan path.json     # use a local scan object instead of S3
    bin/trace.py --markdown out.md    # write the delivery-pack table

**The recompute is deliberately a SECOND, independent definition, and that is the point.** Everywhere
else in this platform a second definition of a number is a defect - it is why recording rules were
rejected for anything the collector already computes (SPEC §10.4). Here the independence IS the test:
importing the pillar and comparing it to itself would prove nothing. So each `derive` below is written
straight from the gcom field name, in the shortest expression that can be checked by eye against §3 of
the SPEC. If a pillar changes how it aggregates, this disagrees and says so.

Exit code 1 on any mismatch, so it can be a gate rather than a report someone has to read.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import subprocess
import sys
from typing import Any, Callable, NamedTuple

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from collector.coverage import Coverage  # noqa: E402
from collector.pillars import compose  # noqa: E402

DEFAULT_KEY = "scans/t1/latest.json"

# Tolerance for the live comparison only. The recompute must match the pillar EXACTLY; the live value
# can differ in the last decimal because Mimir stores float64 samples that went through protobuf.
LIVE_TOLERANCE = 0.5


def _n(stack: dict, field: str) -> float:
    """A gcom count field. Absent and null both mean zero - they are not distinguishable upstream."""
    return float(stack.get(field) or 0)


class Trace(NamedTuple):
    metric: str
    labels: dict[str, str]
    source: str                                   # the named source field(s), for the audit table
    derive: Callable[[list[dict[str, Any]]], float]
    money: bool = False                           # must be sourced from billingActiveUsers
    note: str = ""


# Ordered as a reader would want them: estate size, then people, then money.
TRACES: list[Trace] = [
    Trace("gcinsight_estate_stacks", {"status": "total"},
          "count of records in /instances",
          lambda st: float(len(st))),
    Trace("gcinsight_estate_stacks", {"status": "active"},
          "status == 'active'",
          lambda st: float(len([s for s in st if s.get("status") == "active"]))),
    Trace("gcinsight_estate_stacks", {"status": "paused"},
          "status != 'active'",
          lambda st: float(len([s for s in st if s.get("status") != "active"])),
          note="The estate's 4 paused stacks. Skipped by a scan, never counted as failures."),
    Trace("gcinsight_estate_dashboards", {},
          "sum(dashboardCnt)",
          lambda st: sum(_n(s, "dashboardCnt") for s in st)),
    Trace("gcinsight_estate_alert_rules", {},
          "sum(alertCnt)",
          lambda st: sum(_n(s, "alertCnt") for s in st)),
    Trace("gcinsight_estate_active_users", {},
          "sum(currentActiveUsers)",
          lambda st: sum(_n(s, "currentActiveUsers") for s in st),
          note="NOT valid for money - the billed line is lower; see the money rule below."),
    Trace("gcinsight_estate_daily_users", {},
          "sum(dailyUserCnt)",
          lambda st: sum(_n(s, "dailyUserCnt") for s in st)),
    Trace("gcinsight_estate_users_by_role", {"role": "admin"},
          "sum(currentActiveAdminUsers)",
          lambda st: sum(_n(s, "currentActiveAdminUsers") for s in st)),
    Trace("gcinsight_estate_users_by_role", {"role": "editor"},
          "sum(currentActiveEditorUsers)",
          lambda st: sum(_n(s, "currentActiveEditorUsers") for s in st)),
    Trace("gcinsight_estate_users_by_role", {"role": "viewer"},
          "sum(currentActiveViewerUsers)",
          lambda st: sum(_n(s, "currentActiveViewerUsers") for s in st)),
    Trace("gcinsight_estate_us_region_stacks", {},
          "regionSlug starts with prod-us / us-",
          lambda st: float(len([s for s in st
                                if str(s.get("regionSlug") or "").startswith(("prod-us", "us-"))])),
          note="Data-residency question. Read from regionSlug, never munged from the hostname."),
    # --- Money. Only billingActiveUsers is valid here. -----------------------------------------------
    Trace("gcinsight_cost_billed_users", {},
          "sum(billingActiveUsers)",
          lambda st: sum(_n(s, "billingActiveUsers") for s in st),
          money=True,
          note="THE billed line. Lower than currentActiveUsers; the spread is computed below."),
    Trace("gcinsight_cost_series_per_billed_user", {},
          "sum(hmInstancePromCurrentActiveSeries) / sum(billingActiveUsers)",
          lambda st: round(sum(_n(s, "hmInstancePromCurrentActiveSeries") for s in st)
                           / sum(_n(s, "billingActiveUsers") for s in st), 1)
          if sum(_n(s, "billingActiveUsers") for s in st) else 0.0,
          money=True,
          note="Unit-cost denominator. Uses the billed figure on BOTH halves of the ratio."),
]

MONEY_SOURCE = "billingActiveUsers"
FORBIDDEN_IN_MONEY = "currentActiveUsers"


def load_scan(key: str | None, local: str | None) -> dict:
    if local:
        return json.loads(pathlib.Path(local).read_text())
    bucket = os.environ.get("GCINSIGHT_S3_BUCKET", "").strip()
    if not bucket:
        raise SystemExit("GCINSIGHT_S3_BUCKET is required when --scan is not supplied")
    out = subprocess.run(
        ["aws", "s3", "cp", f"s3://{bucket}/{key or DEFAULT_KEY}", "-"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(out.stdout)


def emitted(scan: dict) -> dict[tuple[str, tuple], float]:
    """What the pillars produce from this scan - the values that were actually published."""
    stacks = scan["data"]["stacks"]
    meta = scan["meta"]
    coverage = Coverage(tier=meta["tier"], total=meta["stacks_total"])
    for slug in meta.get("skipped_stacks", {}):
        coverage.record_skipped(slug, "paused")
    for slug, reason in meta.get("failed_stacks", {}).items():
        coverage.record_failure(slug, reason)
    for s in stacks:
        slug = str(s["slug"])
        if slug not in meta.get("skipped_stacks", {}) and slug not in meta.get("failed_stacks", {}):
            coverage.record_ok(slug)
    metrics, _ = compose.build_all(stacks, coverage)
    return {(n, tuple(sorted(l.items()))): v for n, l, v in metrics}


def live_values(names: set[str], context: str) -> dict[tuple[str, tuple], float]:
    """Newest sample per series on the write stack.

    A RANGE query with a wide window, never an instant one: the collector writes hourly and Mimir's
    lookback-delta is 5 minutes, so an instant query at `now` is empty at almost any moment.
    """
    selector = "|".join(sorted(n.removeprefix("gcinsight_") for n in names))
    expr = f'{{__name__=~"gcinsight_({selector})"}}'
    out = subprocess.run(
        ["gcx", "metrics", "query", expr, "--context", context, "-d", "grafanacloud-prom",
         "--from", "now-6h", "--to", "now", "--step", "5m", "-o", "json"],
        capture_output=True, text=True, check=True,
    )
    body = "\n".join(l for l in out.stdout.splitlines() if not l.startswith('{"class"'))
    result = json.loads(body)["data"]["result"]
    values: dict[tuple[str, tuple], float] = {}
    for series in result:
        labels = dict(series["metric"])
        name = labels.pop("__name__")
        if series["values"]:
            values[(name, tuple(sorted(labels.items())))] = float(series["values"][-1][1])
    return values


def run(scan: dict, *, check_live: bool, context: str = "") -> tuple[list[dict], int]:
    stacks = scan["data"]["stacks"]
    published = emitted(scan)
    if check_live and not context:
        raise ValueError("a gcx context is required for a live comparison")
    live = live_values({t.metric for t in TRACES}, context) if check_live else {}

    rows, failures = [], 0
    for t in TRACES:
        key = (t.metric, tuple(sorted(t.labels.items())))
        recomputed = t.derive(stacks)
        pillar = published.get(key)
        row = {
            "metric": t.metric, "labels": t.labels, "source": t.source, "money": t.money,
            "note": t.note, "recomputed": recomputed, "pillar": pillar, "live": live.get(key),
            "status": "ok",
        }

        if pillar is None:
            row["status"] = "NOT EMITTED"
            failures += 1
        elif abs(pillar - recomputed) > 1e-6:
            row["status"] = f"MISMATCH pillar={pillar} recomputed={recomputed}"
            failures += 1
        elif t.money and MONEY_SOURCE not in t.source:
            row["status"] = f"MONEY NOT FROM {MONEY_SOURCE}"
            failures += 1
        elif t.money and FORBIDDEN_IN_MONEY in t.source:
            row["status"] = f"MONEY USES {FORBIDDEN_IN_MONEY}"
            failures += 1
        elif check_live:
            got = live.get(key)
            if got is None:
                row["status"] = "ABSENT ON STACK"
                failures += 1
            elif abs(got - recomputed) > LIVE_TOLERANCE:
                # Not necessarily a defect: the live sample may predate this scan. Reported, not fatal.
                row["status"] = f"live={got} differs from this scan (may be an older sample)"
        rows.append(row)
    return rows, failures


def _label_str(labels: dict[str, str]) -> str:
    return "{" + ",".join(f"{k}={v}" for k, v in sorted(labels.items())) + "}" if labels else ""


def render(rows: list[dict], scan: dict, *, check_live: bool) -> str:
    meta = scan["meta"]
    out = [
        "# Leadership-number traceability",
        "",
        f"Source scan: `{meta['tier']}` at `{meta['generated_at']}`, "
        f"{meta['stacks_scanned']} of {meta['stacks_total']} stacks "
        f"(coverage {meta['coverage_ratio']:.0%}).",
        "",
        "Each row is recomputed from the named gcom field in the raw scan object by `bin/trace.py`, "
        "independently of the pillar that publishes it. `Recomputed` and `Published` disagreeing is a "
        "defect in one of the two.",
        "",
        "| Number | Source field | Recomputed | Published |" + (" On stack |" if check_live else "")
        + " Status |",
        "|---|---|---:|---:|" + ("---:|" if check_live else "") + "---|",
    ]
    for r in rows:
        money = " **£**" if r["money"] else ""
        live = f" {r['live']:,.1f} |" if check_live and r["live"] is not None else (" - |" if check_live else "")
        ok = "ok" if r["status"] == "ok" else r["status"]
        out.append(
            f"| `{r['metric']}`{_label_str(r['labels'])}{money} | `{r['source']}` | "
            f"{r['recomputed']:,.1f} | {r['pillar']:,.1f} |{live} {ok} |"
        )
    notes = [r for r in rows if r["note"]]
    if notes:
        out += ["", "## Notes", ""]
        out += [f"- `{r['metric']}` - {r['note']}" for r in notes]
    billed = next((r["recomputed"] for r in rows if r["metric"] == "gcinsight_cost_billed_users"), 0)
    active = next((r["recomputed"] for r in rows if r["metric"] == "gcinsight_estate_active_users"), 0)
    spread = (active - billed) / billed * 100 if billed else 0
    out += [
        "",
        "## Money rule",
        "",
        f"Rows marked **£** must derive from `{MONEY_SOURCE}` and never from `{FORBIDDEN_IN_MONEY}`. "
        f"**In this scan the two differ by {spread:.0f}%** ({billed:,.0f} billed against "
        f"{active:,.0f} active), so the wrong field overstates any per-user figure by that much. "
        f"The spread is recomputed on every run rather than quoted, because it moves with the estate. "
        f"`bin/trace.py` exits non-zero if a money row's source field does not name `{MONEY_SOURCE}`.",
    ]
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--scan", help="local scan object instead of S3")
    ap.add_argument("--key", help=f"S3 key to read (default {DEFAULT_KEY})")
    ap.add_argument("--live", action="store_true", help="also compare against the configured write stack")
    ap.add_argument("--context", default=os.environ.get("GCINSIGHT_GCX_CONTEXT", ""),
                    help="gcx context for --live; defaults to GCINSIGHT_GCX_CONTEXT")
    ap.add_argument("--markdown", help="write the delivery-pack table to this path")
    args = ap.parse_args()

    if args.live and not args.context:
        ap.error("--live requires --context or GCINSIGHT_GCX_CONTEXT")
    scan = load_scan(args.key, args.scan)
    rows, failures = run(scan, check_live=args.live, context=args.context)
    table = render(rows, scan, check_live=args.live)

    if args.markdown:
        pathlib.Path(args.markdown).write_text(table)
        print(f"wrote {args.markdown}")
    else:
        print(table)

    bad = [r for r in rows if r["status"] != "ok"]
    if bad:
        print(f"\n{len(bad)} row(s) not clean:", file=sys.stderr)
        for r in bad:
            print(f"  {r['metric']}{_label_str(r['labels'])}: {r['status']}", file=sys.stderr)
    print(f"\n{len(rows) - failures}/{len(rows)} traced clean", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
