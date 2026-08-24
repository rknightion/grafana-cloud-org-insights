"""Carry-forward for weekly metrics (PLAN 5.3, SPEC §5.3).

**The problem, measured.** A T1 run emits 642 series; a T3 run emits 1,254. The extra 612 - every
maturity score, every Adaptive recommendation count, every cardinality figure - come from the weekly
data-plane sweep. Mimir resolves an instant query using `lookback-delta`, 5 minutes by default. A series
with one sample a week is therefore queryable for **5 minutes in every 10,080**, and for the remaining
99.95% of the week every Pillar B, D and F panel renders "No data".

Nobody diagnoses that as a cadence problem. They conclude the dashboard is broken.

**The fix.** T3 writes its metric batch to S3 as state; T1 reads it hourly and re-emits any series it
does not compute itself, stamped with the *current* time. It adds **no new series** - they are the same
series, already counted active - and it keeps alerting on them working.

**Two ways this could lie, and what stops each:**

- *A stale carry-forward looks healthy forever.* If T3 breaks, T1 would keep re-publishing last week's
  maturity scores as current. So carrying stops at `MAX_CARRY_AGE` and
  `gcinsight_carry_forward_age_seconds{tier}` is always emitted - alert on **its age**, exactly as
  with the dead-man's switch (PLAN 1.8). Better a panel that goes empty than one that is confidently wrong.
- *Carrying a series the live tier also computes.* That would put two samples for one series in one
  batch, and remote_write would keep whichever encoded last. `carry_forward` filters against the live
  batch by `(name, labels)`, and the emitter's duplicate guard is the backstop.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Collection, Mapping, Sequence

from collector import identity

# **Must be re-derived whenever T3's cadence changes.** It was 14 days when T3 was weekly (two missed
# runs). T3 moved to every 6 hours on 2026-08-19, and leaving it at 14 days would have meant 56
# consecutive missed runs still presenting as current - the exact failure this cap exists to prevent,
# just slower to notice.
#
# 3 days is 12 missed runs: generous enough that a weekend of infrastructure trouble does not blank the
# panels, short enough that nobody reads a stale batch as fresh. It must stay LONGER than the t3
# staleness alert threshold (18h) so the alert always fires before the panels go empty, rather than the
# other way round - `tests/test_alerts.py` asserts that ordering for every tier.
MAX_CARRY_AGE = dt.timedelta(days=3)

STATE_PREFIX = "state"

Metric = tuple[str, Mapping[str, str], float]


class StateUnavailable(RuntimeError):
    """No carry-forward state to read. Not an error on a first run."""


def state_key(tier: str) -> str:
    return f"{STATE_PREFIX}/{tier}-metrics.json"


def save_state(
    metrics: Sequence[Metric], tier: str, *, bucket: str, now: dt.datetime | None = None,
    dry_run: bool = False,
) -> str:
    """Persist a tier's batch so a faster tier can republish it."""
    stamp = (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds")
    payload = {
        "generated_at": stamp,
        "tier": tier,
        "metrics": [[name, dict(labels), value] for name, labels, value in metrics],
    }
    key = state_key(tier)
    uri = f"s3://{bucket}/{key}"
    if dry_run:
        return f"DRY-RUN {uri}"
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "state.json"
        path.write_text(json.dumps(payload))
        proc = subprocess.run(
            ["aws", "s3", "cp", str(path), uri, "--region", "eu-west-1", "--only-show-errors"],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"{uri}: {proc.stderr.strip()}")
    return uri


def load_state(tier: str, *, bucket: str) -> dict[str, Any]:
    proc = subprocess.run(
        ["aws", "s3", "cp", f"s3://{bucket}/{state_key(tier)}", "-", "--region", "eu-west-1"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise StateUnavailable(f"{state_key(tier)}: {proc.stderr.strip()}")
    try:
        state = json.loads(proc.stdout)
        for metric in state.get("metrics", []):
            if isinstance(metric, list) and metric:
                metric[0] = identity.canonical_metric_name(str(metric[0]))
        return state
    except json.JSONDecodeError as exc:
        raise StateUnavailable(f"{state_key(tier)}: not JSON ({exc})") from exc


def carry_forward(
    live: Sequence[Metric],
    state: Mapping[str, Any] | None,
    *,
    now: dt.datetime | None = None,
    max_age: dt.timedelta = MAX_CARRY_AGE,
    live_stacks: Collection[str] | None = None,
) -> tuple[list[Metric], dict[str, Any]]:
    """Return `(extra_metrics, report)`.

    `extra_metrics` are the state's series minus anything already in `live`. `report` always carries
    `age_seconds` and `carried`, so a dashboard can show why a panel is empty.

    `live_stacks` is the slug set from THIS run's inventory. Any carried series labelled with a stack
    outside it is dropped: the estate is re-discovered every run, so a stack missing from the current
    inventory has left the org, and re-stamping its last T3 score with the current time would show a
    decommissioned stack as live for up to `MAX_CARRY_AGE`.

    An **empty** `live_stacks` is treated as *unknown*, not as an estate of zero stacks - an inventory
    call that returned nothing is a failure, and honouring it literally would blank every per-stack
    series at once. `None` (no inventory to hand) carries everything, as before.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    report: dict[str, Any] = {
        "available": False, "age_seconds": None, "carried": 0, "skipped_live": 0,
        "dropped_absent": 0, "source_tier": None, "too_old": False,
    }
    if not state:
        return [], report

    report["available"] = True
    report["source_tier"] = state.get("tier")
    try:
        generated = dt.datetime.fromisoformat(str(state["generated_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError):
        report["too_old"] = True
        return [], report

    age = now - generated
    report["age_seconds"] = round(age.total_seconds())
    if age > max_age:
        # Deliberately republish nothing. An empty panel beats a confidently wrong one.
        report["too_old"] = True
        return [], report

    own = {(name, tuple(sorted(dict(labels).items()))) for name, labels, _ in live}
    known = set(live_stacks) if live_stacks else None
    extra: list[Metric] = []
    for name, labels, value in state.get("metrics", []):
        key = (name, tuple(sorted(dict(labels).items())))
        if key in own:
            report["skipped_live"] += 1
            continue
        # A series with no `stack` label is an estate rollup and belongs to no single stack.
        stack = dict(labels).get("stack")
        if known is not None and stack is not None and stack not in known:
            report["dropped_absent"] += 1
            continue
        extra.append((name, dict(labels), float(value)))
    report["carried"] = len(extra)
    return extra, report


def report_metrics(report: Mapping[str, Any], tier: str) -> list[Metric]:
    """Make the carry-forward's own health queryable. Alert on the AGE, not on the count."""
    out: list[Metric] = [
        ("gcinsight_carry_forward_series", {"tier": tier}, float(report.get("carried") or 0)),
        # Always emitted, including as 0. A stack leaving the estate is a real event, and a silent
        # drop would be indistinguishable from a carry that never had those series in the first place.
        ("gcinsight_carry_forward_dropped_absent", {"tier": tier},
         float(report.get("dropped_absent") or 0)),
    ]
    if report.get("age_seconds") is not None:
        out.append(
            ("gcinsight_carry_forward_age_seconds", {"tier": tier},
             float(report["age_seconds"]))
        )
    return out
