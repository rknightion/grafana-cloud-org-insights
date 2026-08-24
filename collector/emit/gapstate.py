"""When a stack's credential gap was FIRST seen - the input to the coverage alert (PLAN 17D).

## Why a count cannot be the alert

The requirement is to be told when a stack has been missing its credential for two or three days. The obvious
implementation is a Grafana rule on `gcinsight_stacks_missing_credential > 0 FOR 48h`, and it is
wrong: the condition is true whenever *any* stack has a gap, and a live org creates stacks steadily. A
succession of stacks each missing for a few hours keeps the count above zero continuously, so the `for`
clause never resets and the rule fires having never seen a single gap last 48 hours.

So the age of the OLDEST INDIVIDUAL gap is the alertable quantity, and computing it needs the one thing a
stateless scan does not have: when each gap started. Same principle as the dead-man's switch and
carry-forward - alert on an age, never on a count.

## Why this is not "putting inventory in a config store"

The golden rule forbids storing the estate or its provisioning state, because that replaces discovery
with configuration and lets the two drift. This stores neither: it is a record of **when we first
observed** something, which is history and cannot be discovered by definition. It is authoritative about
nothing - every slug in it is re-derived from the live inventory each run, and a slug that has healed or
left the estate is dropped, not kept.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Collection, Mapping

from collector.emit import s3 as s3emit

KEY = "state/credential-gaps.json"


def _read(bucket: str, runner: Callable[..., Any]) -> dict[str, Any]:
    proc = runner(["aws", "s3", "cp", f"s3://{bucket}/{KEY}", "-", "--region", s3emit.REGION],
                  capture_output=True, text=True)
    if proc.returncode != 0:
        return {}
    try:
        body = json.loads(proc.stdout or "{}")
    except ValueError:
        return {}
    seen = body.get("first_seen")
    return seen if isinstance(seen, dict) else {}


def _write(state: Mapping[str, str], bucket: str, runner: Callable[..., Any]) -> None:
    payload = {"_note": "when each stack's credential gap was first observed; see emit/gapstate.py",
               "first_seen": dict(state)}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gaps.json"
        path.write_text(json.dumps(payload, indent=1, sort_keys=True))
        runner(["aws", "s3", "cp", str(path), f"s3://{bucket}/{KEY}", "--region", s3emit.REGION,
                "--only-show-errors"], capture_output=True, text=True)


def merge(previous: Mapping[str, str], missing: Collection[str],
          now: dt.datetime | None = None) -> dict[str, str]:
    """Carry forward the first-seen stamp of a gap that persists; stamp a new one; drop a healed one.

    Dropping is the half that matters: a slug left behind after the provisioner fixed it, or after the
    stack was decommissioned, would keep reporting an ever-growing age and hold the alert on for ever.
    """
    stamp = (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds")
    return {slug: str(previous.get(slug) or stamp) for slug in sorted(missing)}


def oldest_age_seconds(state: Mapping[str, str], now: dt.datetime | None = None) -> float | None:
    """Age of the longest-standing gap, or `None` when there is no gap or no parseable stamp.

    `None` rather than 0.0 on purpose: a zero reads as "a gap that started this instant", which is a
    different fact from "there are no gaps" and would make the alert's own metric indistinguishable
    from a healthy estate at the exact moment a stack is created.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    ages: list[float] = []
    for stamp in state.values():
        try:
            then = dt.datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        if then.tzinfo is None:
            then = then.replace(tzinfo=dt.timezone.utc)
        ages.append((now - then).total_seconds())
    return max(ages) if ages else None


def load(*, bucket: str = s3emit.BUCKET, runner: Callable[..., Any] = subprocess.run) -> dict[str, str]:
    """Read the stamps without writing. For a tier that HYDRATES the Assistant input rather than
    gathering it: it must be able to report an age, and it must not stamp gaps it did not observe."""
    return _read(bucket, runner)


def update(
    missing: Collection[str],
    *,
    bucket: str = s3emit.BUCKET,
    now: dt.datetime | None = None,
    dry_run: bool = False,
    runner: Callable[..., Any] = subprocess.run,
) -> dict[str, str]:
    """Read, merge, write. Returns the merged state; a dry run computes it and writes nothing."""
    state = merge(_read(bucket, runner), missing, now)
    if not dry_run:
        _write(state, bucket, runner)
    return state
