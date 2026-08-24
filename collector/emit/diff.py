"""T4 estate diff - what changed, over two windows (PLAN 5.6, 13.2).

**The selection is the risky part, not the subtraction.** "Diff the two most recent scans" is the obvious
implementation and it is wrong: T1 runs hourly, so the two most recent T1 scans are an hour apart, and
the result would be an hour-over-hour delta published under a weekly label. Nobody would notice - the
numbers would look plausible and simply be answering a different question.

So a diff selects **the latest scan and the one nearest its window's target**, and the output carries both
timestamps and the *actual* interval achieved. If the nearest candidate to `T-7d` is 4 days old, the report
says 4 days rather than implying 7.

## Two windows since 2026-08-19, and they must not bleed into each other

T4 moved from weekly to daily, so it publishes a **1-day** diff alongside the **7-day** one. Adding a
second window multiplies the ways the original defect can reappear, so each window owns its whole
contract - target, minimum, maximum, tolerance and view key - in `WINDOWS`:

- **A shared minimum** would either let the weekly diff run on a 20-hour baseline, or stop the daily one
  ever running. The weekly floor is 1 day; the daily floor is 12 hours.
- **A shared maximum** is worse and less obvious: with `MAX_INTERVAL` at 21 days for both, a daily diff
  taken while T3 had been down for a week would happily compare against a 7-day-old scan and publish it
  as "daily". The daily maximum is 3 days.
- **A shared `on_target` tolerance** of 1 day is right for a 7-day target and meaningless for a 1-day one
  - it would call a 2-day interval on target. Tolerance is per window.
- **A shared view key** would mean whichever diff ran last silently overwrote the other.

`tests/test_diff.py` asserts each of those separately, because every one of them produces a report that
looks correct and answers a different question than its label claims.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from typing import Any, Mapping, NamedTuple, Sequence

TARGET_INTERVAL = dt.timedelta(days=7)
# A baseline closer than this cannot answer "what changed this week".
MIN_INTERVAL = dt.timedelta(days=1)
# Nor can one this far out; past it, say so instead of comparing.
MAX_INTERVAL = dt.timedelta(days=21)


class Window(NamedTuple):
    """One diff window's complete contract. Nothing about a window is defined anywhere else."""

    name: str
    target: dt.timedelta
    min_interval: dt.timedelta   # below this the label is a lie
    max_interval: dt.timedelta   # above this, refuse rather than compare
    tolerance: dt.timedelta      # how far off target still counts as `on_target`
    view: str                    # S3 view key - must be unique per window
    label: str                   # human phrase for the report


WINDOWS: tuple[Window, ...] = (
    # `estate_diff` keeps its key for continuity of the S3 object, NOT because a panel was bound to it -
    # measured 2026-08-19, NOTHING rendered it. T4 had been publishing this view since deployment with no
    # panel anywhere, so the diff existed and nobody could see it. Both windows now have a table on the
    # estate dashboard's "Change" tab.
    Window("weekly", dt.timedelta(days=7), MIN_INTERVAL, MAX_INTERVAL,
           dt.timedelta(days=1), "estate_diff", "week over week"),
    # 12h floor: T3 runs every 6 hours, so a 12-hour baseline is two runs back and a real interval.
    # 3-day ceiling: past that "daily" is false, and the weekly window is the one that should answer.
    Window("daily", dt.timedelta(days=1), dt.timedelta(hours=12), dt.timedelta(days=3),
           dt.timedelta(hours=8), "estate_diff_daily", "day over day"),
)

WEEKLY, DAILY = WINDOWS

# Estate-level figures worth a week-over-week line. Deliberately short: a diff of everything is a wall.
TRACKED = (
    ("stacks", "Stacks"),
    ("active_series", "Active series"),
    ("billed_users", "Billed users"),
    ("active_users", "Active users"),
    ("dashboards", "Dashboards"),
    ("alert_rules", "Alert rules"),
    ("adaptive_pending", "Adaptive recommendations pending"),
    ("adaptive_applied", "Adaptive rules applied"),
    ("collectors", "Fleet collectors"),
    ("label_values", "Label values (total)"),
)


class NoBaseline(RuntimeError):
    """Nothing suitable to compare against. Not an error on a young deployment."""


def list_scans(tier: str, *, bucket: str) -> list[tuple[str, dt.datetime]]:
    """Every timestamped scan for a tier, newest first. `latest.json` is excluded - it is a duplicate."""
    proc = subprocess.run(
        ["aws", "s3", "ls", f"s3://{bucket}/scans/{tier}/", "--region", "eu-west-1"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise NoBaseline(f"cannot list scans/{tier}/: {proc.stderr.strip()}")
    out: list[tuple[str, dt.datetime]] = []
    for line in proc.stdout.splitlines():
        parts = line.split()
        if not parts:
            continue
        name = parts[-1]
        if not name.endswith(".json") or name == "latest.json":
            continue
        stamp = parse_key_timestamp(name)
        if stamp:
            # `aws s3 ls <prefix>/` prints the object NAME, not the full key. Returning it bare makes
            # load_scan look at the bucket root and 404.
            out.append((f"scans/{tier}/{name}", stamp))
    return sorted(out, key=lambda pair: pair[1], reverse=True)


def parse_key_timestamp(key: str) -> dt.datetime | None:
    """`20260817T200302+0000.json` → aware datetime. Written by `emit/s3.py:write_scan`."""
    stem = key.rsplit("/", 1)[-1].removesuffix(".json")
    try:
        return dt.datetime.strptime(stem, "%Y%m%dT%H%M%S%z")
    except ValueError:
        return None


def select_baseline(
    scans: Sequence[tuple[str, dt.datetime]],
    *,
    now: dt.datetime | None = None,
    window: Window = WEEKLY,
    target: dt.timedelta | None = None,
) -> tuple[tuple[str, dt.datetime], tuple[str, dt.datetime]]:
    """Return `(latest, baseline)`, the baseline being the candidate nearest `now - window.target`.

    NOT "the two most recent" - with hourly T1 scans that yields an hour-over-hour delta wearing a
    weekly label. Every bound comes from `window`, so the two windows cannot relax each other.

    `target` is accepted for callers that predate `WINDOWS` and overrides `window.target` alone; the
    minimum and maximum still come from the window.
    """
    if len(scans) < 2:
        raise NoBaseline(f"need two scans to diff, have {len(scans)}")
    ordered = sorted(scans, key=lambda pair: pair[1], reverse=True)
    latest = ordered[0]
    now = now or latest[1]
    wanted = now - (target or window.target)

    candidates = [pair for pair in ordered[1:] if latest[1] - pair[1] >= window.min_interval]
    if not candidates:
        gap = latest[1] - ordered[1][1]
        raise NoBaseline(
            f"nearest other scan is {gap} old; a {window.name} comparison needs at least "
            f"{window.min_interval}"
        )
    baseline = min(candidates, key=lambda pair: abs(pair[1] - wanted))
    if latest[1] - baseline[1] > window.max_interval:
        raise NoBaseline(
            f"nearest usable baseline for the {window.name} window is "
            f"{latest[1] - baseline[1]} old, beyond {window.max_interval}"
        )
    return latest, baseline


def load_scan(key: str, *, bucket: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["aws", "s3", "cp", f"s3://{bucket}/{key}", "-", "--region", "eu-west-1"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise NoBaseline(f"cannot read {key}: {proc.stderr.strip()}")
    return json.loads(proc.stdout)


def summarise(scan: Mapping[str, Any]) -> dict[str, float]:
    """Reduce a scan envelope to the tracked estate figures. Missing inputs are absent, not zero."""
    data = scan.get("data") or {}
    stacks = data.get("stacks") or []
    dataplane = data.get("dataplane") or {}
    out: dict[str, float] = {}
    if stacks:
        out["stacks"] = float(len(stacks))
        out["active_series"] = float(
            sum(s.get("hmInstancePromCurrentActiveSeries") or 0 for s in stacks)
        )
        out["billed_users"] = float(sum(s.get("billingActiveUsers") or 0 for s in stacks))
        out["active_users"] = float(sum(s.get("currentActiveUsers") or 0 for s in stacks))
        out["dashboards"] = float(sum(s.get("dashboardCnt") or 0 for s in stacks))
        out["alert_rules"] = float(sum(s.get("alertCnt") or 0 for s in stacks))
    if dataplane:
        adaptive = [
            (v.get("adaptive_metrics") or {}) for v in dataplane.values()
        ]
        measured = [a for a in adaptive if a.get("available")]
        if measured:
            out["adaptive_pending"] = float(
                sum(a.get("recommendations_pending") or 0 for a in measured)
            )
            out["adaptive_applied"] = float(sum(a.get("rules_applied") or 0 for a in measured))
        fleet = [(v.get("fleet") or {}) for v in dataplane.values()]
        if any(f.get("available") for f in fleet):
            out["collectors"] = float(sum(f.get("collectors") or 0 for f in fleet))
        cards = [(v.get("cardinality") or {}) for v in dataplane.values()]
        if any(c.get("available") for c in cards):
            out["label_values"] = float(
                sum(c.get("label_values_count_total") or 0 for c in cards)
            )
    return out


# How far the two sides' measured populations may differ before every summed row becomes misleading.
# 267 vs 269 of ~270 is normal churn; half the estate missing from one side is not. Set loose on purpose -
# this exists to catch a broken scan, not to editorialise about two new stacks.
POPULATION_TOLERANCE = 0.10


def population(scan: Mapping[str, Any]) -> dict[str, int]:
    """How many stacks each half of a scan actually measured.

    Every figure in `TRACKED` is a SUM over whatever stacks were present, so a coverage change and an
    estate change produce the same shape of movement. Reporting the population is what lets a reader tell
    them apart - see `PopulationGuardTest` for the day this was needed.
    """
    data = scan.get("data") or {}
    dataplane = data.get("dataplane") or {}
    measured = [
        v for v in dataplane.values()
        if any((v.get(sig) or {}).get("available")
               for sig in ("cardinality", "fleet", "adaptive_metrics"))
    ]
    return {"inventory": len(data.get("stacks") or []), "dataplane": len(measured)}


def _comparable(now: Mapping[str, int], then: Mapping[str, int]) -> bool:
    """True when both sides measured a similar-sized population, so the sums can be compared."""
    for key in ("inventory", "dataplane"):
        a, b = now.get(key, 0), then.get(key, 0)
        if a == 0 and b == 0:
            continue          # neither side measured it - already handled per row, not a skew
        if max(a, b) == 0:
            return False
        if abs(a - b) / max(a, b) > POPULATION_TOLERANCE:
            return False
    return True


def diff(
    latest: Mapping[str, Any], baseline: Mapping[str, Any],
    latest_at: dt.datetime, baseline_at: dt.datetime,
    window: Window = WEEKLY,
) -> dict[str, Any]:
    """Change over `window`, carrying both timestamps and the interval actually achieved."""
    now_values = summarise(latest)
    then_values = summarise(baseline)
    now_pop, then_pop = population(latest), population(baseline)
    interval = latest_at - baseline_at

    rows: list[dict[str, Any]] = []
    for key, label in TRACKED:
        current, previous = now_values.get(key), then_values.get(key)
        if current is None or previous is None:
            # One side did not measure it. A delta of 0 would claim "no change".
            rows.append({" Metric": label, "Now": current, "Then": previous, "Change": None,
                         "Change %": None, "Note": "not measured in both scans"})
            continue
        delta = current - previous
        rows.append({
            " Metric": label,
            "Now": current,
            "Then": previous,
            "Change": delta,
            "Change %": round(100 * delta / previous, 2) if previous else None,
            "Note": None,
        })

    return {
        "latest_at": latest_at.isoformat(),
        "baseline_at": baseline_at.isoformat(),
        # Stated explicitly and never implied - the baseline is the NEAREST to T-7d, not exactly it.
        "interval_days": round(interval.total_seconds() / 86400, 2),
        "target_interval_days": round(window.target.total_seconds() / 86400, 2),
        "on_target": abs(interval - window.target) <= window.tolerance,
        "window": window.name,
        "window_label": window.label,
        "population": {
            "now": now_pop,
            "then": then_pop,
            "comparable": _comparable(now_pop, then_pop),
            "tolerance": POPULATION_TOLERANCE,
        },
        "rows": rows,
    }


def as_view(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The diff as a table, led by a row stating the real interval so no reader assumes the target.

    The header names the window as well as the interval: two diff tables on one dashboard are
    indistinguishable otherwise, and a reader who mistakes the daily table for the weekly one draws a
    conclusion seven times too strong.
    """
    # Render a whole number of days without a decimal: "target was 7 days", not "7.0 days".
    raw = report["target_interval_days"]
    target = int(raw) if float(raw).is_integer() else raw
    label = report.get("window_label", "")
    header = {
        " Metric": "COMPARISON WINDOW",
        "Now": report["latest_at"],
        "Then": report["baseline_at"],
        "Change": f"{report['interval_days']} days",
        "Change %": None,
        "Note": f"{label} - on target ({target}d)" if report["on_target"]
        else f"{label} - target was {target} days - read the actual interval",
    }
    rows = [header]
    # Only shown when it matters. A population row on every clean diff would be noise, and noise on a
    # governance table is how people stop reading the header rows that DO matter.
    pop = report.get("population")
    if pop and not pop.get("comparable", True):
        rows.append({
            " Metric": "POPULATION",
            "Now": f"{pop['now']['inventory']} stacks / {pop['now']['dataplane']} data plane",
            "Then": f"{pop['then']['inventory']} stacks / {pop['then']['dataplane']} data plane",
            "Change": None,
            "Change %": None,
            "Note": "the two scans measured DIFFERENT populations - every row below is a sum over "
                    "whatever was measured, so this is a coverage difference and not necessarily an "
                    "estate change. Check the failing tier before quoting any figure.",
        })
    return rows + list(report["rows"])
