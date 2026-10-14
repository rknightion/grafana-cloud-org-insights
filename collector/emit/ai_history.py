"""Bounded, aggregate-only AI observations; dated MTD records are never invoices.

The caller owns full-estate/source/publication admission. This helper refuses empty inventory,
unavailable snapshots and unverified rollover, and uses S3 conditional writes to preserve a
concurrent bootstrap. Billing and one-time BI observations remain separate source/month records.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from collector.emit import s3 as s3emit
from collector.emit.carry import MAX_FUTURE_SKEW

KEY = "state/ai-cost-history.json"
SCHEMA_VERSION = 1
MAX_BYTES = 2 * 1024 * 1024
MAX_MONTHS = 13
MAX_ROWS = 20_000
AWS_TIMEOUT = 30
SOURCES = frozenset({"billing_observation", "bi_one_time"})
ORG_FIELDS = frozenset({"users", "service_users", "user_tokens", "service_tokens", "user_excess",
                        "users_over_allowance", "system_excess", "billed_overage"})
STACK_FIELDS = frozenset({"users", "service_users", "user_tokens", "service_tokens", "user_excess",
                          "billed_overage"})
INTEGER_FIELDS = frozenset({"users", "service_users", "user_tokens", "service_tokens",
                            "users_over_allowance"})
SNAPSHOT_FIELDS = frozenset({"available", "source", "query_time", "captured_month", "period_status",
                             "personal_allowance", "system_allowance", "org", "stacks"})


class HistoryError(RuntimeError):
    """Closed reason codes only: never include raw data, AWS output or exception text."""


def _now(now: dt.datetime | None) -> dt.datetime:
    current = now or dt.datetime.now(dt.timezone.utc)
    if not isinstance(current, dt.datetime) or current.tzinfo is None:
        raise HistoryError("invalid_clock")
    return current.astimezone(dt.timezone.utc)


def _encoded(value: Any, reason: str) -> bytes:
    try:
        result = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    except (TypeError, ValueError, OverflowError):
        raise HistoryError(reason) from None
    if len(result) > MAX_BYTES:
        raise HistoryError(reason)
    return result


def _time(value: Any, current: dt.datetime, reason: str) -> dt.datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise HistoryError(reason)
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (stamp.tzinfo is None or stamp.utcoffset() != dt.timedelta(0)
                or stamp > current + MAX_FUTURE_SKEW):
            raise ValueError
    except (ValueError, TypeError, OverflowError):
        raise HistoryError(reason) from None
    return stamp


def _numeric(value: Any, *, integer: bool, nullable: bool, reason: str) -> Any:
    if value is None and nullable:
        return None
    if (type(value) not in (int, float) or (integer and type(value) is not int)
            or not 0 <= value <= 2**53 or not math.isfinite(value)):
        raise HistoryError(reason)
    return value


def _aggregates(value: Any, fields: frozenset[str], *, nullable: bool,
                reason: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        raise HistoryError(reason)
    return {key: _numeric(value[key], integer=key in INTEGER_FIELDS,
                          nullable=nullable or key == "billed_overage", reason=reason)
            for key in sorted(fields)}


def _snapshot(value: Any, current: dt.datetime, reason: str,
              *, allow_rollover: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) not in (SNAPSHOT_FIELDS, SNAPSHOT_FIELDS | {"provenance"}):
        raise HistoryError(reason)
    if (value["available"] is not True or not isinstance(value["source"], str)
            or value["source"] not in SOURCES):
        raise HistoryError(reason)
    stamp = _time(value["query_time"], current, reason)
    month = value["captured_month"]
    if not isinstance(month, str) or month != stamp.strftime("%Y-%m"):
        raise HistoryError(reason)
    period = value["period_status"]
    if period != "observed_mtd" and not (allow_rollover and period == "rollover_unverified"):
        raise HistoryError(reason)
    # First-day source preview is not sufficient current-period evidence, even if mislabeled.
    if stamp.day == 1 and value["source"] == "billing_observation" and period != "rollover_unverified":
        raise HistoryError(reason)
    personal = _numeric(value["personal_allowance"], integer=True, nullable=False, reason=reason)
    system = _numeric(value["system_allowance"], integer=True, nullable=False, reason=reason)
    org = _aggregates(value["org"], ORG_FIELDS, nullable=False, reason=reason)
    if (org["users_over_allowance"] > org["users"]
            or org["user_excess"] > org["user_tokens"]
            or org["system_excess"] > org["service_tokens"]):
        raise HistoryError(reason)
    raw_stacks = value["stacks"]
    if not isinstance(raw_stacks, Mapping) or len(raw_stacks) > MAX_ROWS:
        raise HistoryError(reason)
    stacks = {}
    for identity, aggregate in raw_stacks.items():
        if not isinstance(identity, str) or not re.fullmatch(r"[1-9][0-9]{0,15}", identity):
            raise HistoryError(reason)
        stacks[identity] = _aggregates(aggregate, STACK_FIELDS, nullable=True, reason=reason)
    result = {"available": True, "source": value["source"], "query_time": value["query_time"],
              "captured_month": month, "period_status": period, "personal_allowance": personal,
              "system_allowance": system, "org": org, "stacks": stacks}
    if "provenance" in value:
        provenance = value["provenance"]
        if (value["source"] != "bi_one_time" or not isinstance(provenance, Mapping)
                or set(provenance) != {"start", "end", "cutover", "query_sha256"}
                or not isinstance(provenance["query_sha256"], str)
                or not re.fullmatch(r"[0-9a-f]{64}", provenance["query_sha256"])):
            raise HistoryError(reason)
        start, end, cutover = (_time(provenance[key], current, reason)
                               for key in ("start", "end", "cutover"))
        if not start < end <= cutover <= stamp or start.strftime("%Y-%m") != month:
            raise HistoryError(reason)
        result["provenance"] = dict(provenance)
    _encoded(result, reason)
    return result


def _history(value: Any, current: dt.datetime) -> list[dict[str, Any]]:
    if not isinstance(value, list) or len(value) > MAX_MONTHS * len(SOURCES):
        raise HistoryError("invalid_history")
    _encoded(value, "invalid_history")
    rows, keys = [], set()
    for raw in value:
        row = _snapshot(raw, current, "invalid_history")
        key = (row["captured_month"], row["source"])
        if key in keys:
            raise HistoryError("invalid_history")
        keys.add(key)
        rows.append(row)
    if (len({row["captured_month"] for row in rows}) > MAX_MONTHS
            or sum(1 + len(row["stacks"]) for row in rows) > MAX_ROWS):
        raise HistoryError("invalid_history")
    return rows


def _live_ids(stacks: Sequence[Mapping[str, Any]]) -> set[str]:
    if not stacks:
        raise HistoryError("empty_inventory")
    result = set()
    for stack in stacks:
        identity = stack.get("id") if isinstance(stack, Mapping) else None
        if type(identity) is not int or not 0 < identity < 10**16 or str(identity) in result:
            raise HistoryError("invalid_inventory")
        result.add(str(identity))
    return result


def merge(previous: list[dict[str, Any]], snapshot: Mapping[str, Any],
          stacks: Sequence[Mapping[str, Any]], now: dt.datetime | None = None) -> list[dict[str, Any]]:
    """Replace only a newer compatible source/month observation; never add MTD values.

    Org totals retain their dated original cohort. Stack rows are left-joined to fresh inventory,
    so they are not evidence of departed stacks still being present.
    """
    current, live = _now(now), _live_ids(stacks)
    history = _history(previous, current)
    candidate = _snapshot(snapshot, current, "invalid_snapshot", allow_rollover=True)
    keyed = {(row["captured_month"], row["source"]): row for row in history}
    if candidate["period_status"] == "observed_mtd":
        key = (candidate["captured_month"], candidate["source"])
        old = keyed.get(key)
        old_time = _time(old["query_time"], current, "invalid_history") if old else None
        candidate_time = _time(candidate["query_time"], current, "invalid_snapshot")
        if old_time is None or old_time < candidate_time:
            keyed[key] = candidate
        elif old_time == candidate_time and old != candidate:
            raise HistoryError("conflicting_observation")
    months = sorted({key[0] for key in keyed}, reverse=True)[:MAX_MONTHS]
    rows = []
    for key in sorted(keyed):
        if key[0] in months:
            row = keyed[key]
            rows.append({**row, "stacks": {identity: aggregate for identity, aggregate in
                                           sorted(row["stacks"].items()) if identity in live}})
    return _history(rows, current)


def _run(args: list[str], runner: Callable[..., Any], reason: str) -> Any:
    try:
        return runner(args, capture_output=True, text=True, timeout=AWS_TIMEOUT)
    except Exception:
        raise HistoryError(reason) from None


def _metadata(raw: Any) -> Mapping[str, Any]:
    if not isinstance(raw, str) or len(raw.encode()) > 16_384:
        raise HistoryError("read_failed")
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        raise HistoryError("read_failed") from None
    if not isinstance(data, Mapping):
        raise HistoryError("read_failed")
    return data


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate field")
        result[key] = value
    return result


def _args(command: str, bucket: str) -> list[str]:
    if not isinstance(bucket, str) or not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", bucket):
        raise HistoryError("invalid_bucket")
    return ["aws", "s3api", command, "--bucket", bucket, "--key", KEY,
            "--region", s3emit.REGION, "--output", "json"]


def _read(bucket: str, runner: Callable[..., Any], current: dt.datetime) -> tuple[list[dict[str, Any]], str | None]:
    head = _run(_args("head-object", bucket), runner, "read_failed")
    if head.returncode != 0:
        # Only exact missing-object service codes permit conditional bootstrap, not 403/auth errors.
        error = head.stderr if isinstance(head.stderr, str) else ""
        if re.search(r"\((?:404|NoSuchKey|NotFound)\) when calling the HeadObject operation", error):
            return [], None
        raise HistoryError("read_failed")
    metadata = _metadata(head.stdout)
    etag, length = metadata.get("ETag"), metadata.get("ContentLength")
    if (not isinstance(etag, str) or not re.fullmatch(r'"[A-Za-z0-9-]{1,128}"', etag)
            or type(length) is not int or not 0 < length <= MAX_BYTES):
        raise HistoryError("read_failed")
    with tempfile.TemporaryDirectory(prefix="gcinsight-ai-history-") as tmp:
        target = Path(tmp) / "history.json"
        proc = _run(_args("get-object", bucket) + ["--if-match", etag, str(target)], runner, "read_failed")
        if proc.returncode != 0 or _metadata(proc.stdout).get("ETag") != etag:
            raise HistoryError("read_failed")
        try:
            if target.stat().st_size != length or target.stat().st_size > MAX_BYTES:
                raise HistoryError("read_failed")
            payload = json.loads(target.read_bytes(), object_pairs_hook=_unique_object)
        except (OSError, ValueError):
            raise HistoryError("invalid_history") from None
    if (not isinstance(payload, Mapping) or set(payload) != {"schema_version", "history"}
            or type(payload["schema_version"]) is not int or payload["schema_version"] != SCHEMA_VERSION):
        raise HistoryError("invalid_history")
    return _history(payload["history"], current), etag


def load(*, bucket: str = s3emit.BUCKET, now: dt.datetime | None = None,
         runner: Callable[..., Any] = subprocess.run) -> list[dict[str, Any]]:
    """Read and validate, without replacing unavailable own-source data or writing."""
    return _read(bucket, runner, _now(now))[0]


def update(snapshot: Mapping[str, Any], stacks: Sequence[Mapping[str, Any]], *,
           bucket: str = s3emit.BUCKET, dry_run: bool = False, now: dt.datetime | None = None,
           runner: Callable[..., Any] = subprocess.run) -> list[dict[str, Any]]:
    """Read/merge/conditionally write; rejected reads and CAS conflicts preserve prior state."""
    current = _now(now)
    # Validate source and inventory before issuing even an S3 read; history is not an input rescue.
    _live_ids(stacks)
    # Root may attach the already minimized history for composition. It is never trusted for state.
    attached = snapshot.get("history")
    if attached is not None:
        _history(attached, current)
    raw = {key: value for key, value in snapshot.items() if key != "history"}
    candidate = _snapshot(raw, current, "invalid_snapshot", allow_rollover=True)
    previous, etag = _read(bucket, runner, current)
    rows = merge(previous, candidate, stacks, current)
    if dry_run or candidate["period_status"] == "rollover_unverified" or rows == previous:
        return rows
    encoded = _encoded({"schema_version": SCHEMA_VERSION, "history": rows}, "invalid_history")
    with tempfile.TemporaryDirectory(prefix="gcinsight-ai-history-") as tmp:
        target = Path(tmp) / "history.json"
        target.write_bytes(encoded)
        conditional = ["--if-match", etag] if etag is not None else ["--if-none-match", "*"]
        proc = _run(_args("put-object", bucket) + ["--body", str(target),
                    "--content-type", "application/json", "--server-side-encryption", "AES256"] +
                    conditional, runner, "write_failed")
        if proc.returncode != 0:
            raise HistoryError("write_failed")
        try:
            acknowledgement = _metadata(proc.stdout)
        except HistoryError:
            raise HistoryError("write_failed") from None
        if not isinstance(acknowledgement.get("ETag"), str):
            raise HistoryError("write_failed")
    return rows
