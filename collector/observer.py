"""Bounded, private evidence of observed collector outcomes.

This process has no inventory authority. Conditional writes protect the distinct
status prefix; recorded acknowledgements are not remote storage receipts.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import selectors
import subprocess
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collector.outcome_events import EVENT_KIND, MAX_EVENT_BYTES, MAX_SEQUENCE, RECEIPT_VIEWS, parse_event, parse_timestamp, validate_event
from collector.runtime_identity import verified_ecs_runtime

TIERS = ("t1", "t2", "t3", "t4")
LOOKBACK_SECONDS = 259200
FRESHNESS_SECONDS = 3600
MAX_OBJECT_BYTES = 262144
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_QUERY_BYTES = 20 * 1024 * 1024
MAX_PAGES = 20
MAX_RECORDS = 10000
MAX_ATTEMPTS = 128
STREAM = re.compile(r"^(t[1-4])/collector/([0-9a-f]{32})$")
TASK = re.compile(r"^[0-9a-f]{32}$")
META_KEYS = {"version", "tier", "generated_at", "observation_started_at", "observation_completed_at", "observation_state", "reason", "status_freshness_seconds", "evidence_max_age_seconds", "authority", "visibility", "current_membership", "actual_latest_outcome"}
ROW_KEYS = {"kind", "view", "attempt_id", "started_at", "observed_at", "state", "reason", "count", "sha256", "last_success_at", "last_success_count", "storage_service_at", "remote_snapshot_at"}
STATE_KEYS = {"attempts", "last_inventory_success", "last_view_success", "observation_high_watermark"}


class ObserverError(Exception):
    """Closed diagnostic only: never include provider or source prose."""


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def encode(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def strict_json(raw: bytes | str):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate")
            result[key] = value
        return result
    def nonfinite(_):
        raise ValueError("nonfinite")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def _time(value, now, *, nullable=False):
    if value is None and nullable:
        return None
    parsed = parse_timestamp(value)
    if parsed is None or parsed > now + timedelta(seconds=300):
        raise ObserverError("invalid_prior")
    return parsed


def _row(kind, view=None):
    return dict(kind=kind, view=view, attempt_id=None, started_at=None,
                observed_at=None, state="unknown", reason="not_observed", count=None,
                sha256=None, last_success_at=None, last_success_count=None,
                storage_service_at=None, remote_snapshot_at=None)


def _identity(event):
    return event["attempt_id"], event["tier"], event["started_at"]


def _event_ref(event):
    return (*_identity(event), event["sequence"])


def _legal_prefix(attempt):
    """Return trustworthy contiguous prefix; malformed transitions trust none."""
    if attempt["conflict"]:
        return [], "conflict"
    events = attempt["events"]
    if events and any(e["source_revision"] != events[0]["source_revision"] for e in events):
        return [], "conflict"
    if not events or events[0]["sequence"] != 1 or events[0]["event"] != "attempt_started":
        return [], "gap"
    prefix = []
    inventory = None
    views = set()
    finished = False
    previous_at = None
    for expected, event in enumerate(events, 1):
        if event["sequence"] != expected:
            return prefix, "gap"
        at = parse_timestamp(event["at"])
        if finished or (previous_at is not None and at < previous_at):
            return [], "conflict"
        name = event["event"]
        if expected == 1:
            if name != "attempt_started":
                return [], "conflict"
        elif name == "inventory_result":
            if inventory is not None or views:
                return [], "conflict"
            inventory = event
        elif name == "view_write_result":
            payload = event["payload"]
            if inventory is None or inventory["payload"]["state"] == "failed" or payload["view"] in views:
                return [], "conflict"
            views.add(payload["view"])
        elif name == "attempt_finished":
            if inventory is None or (event["payload"]["state"] == "success" and inventory["payload"]["state"] == "failed"):
                return [], "conflict"
            finished = True
        else:
            return [], "conflict"
        previous_at = at
        prefix.append(event)
    return prefix, "none"


def validate_projection(value, tier, now):
    """Validate all private replay material before any conditional update."""
    try:
        if type(value) is not dict or set(value) != {"meta", "rows", "_state"} or len(encode(value)) > MAX_OBJECT_BYTES:
            raise ObserverError("invalid_prior")
        meta, rows, state = value["meta"], value["rows"], value["_state"]
        if type(meta) is not dict or set(meta) != META_KEYS or type(meta["version"]) is not int or meta["version"] != 1 or meta["tier"] != tier:
            raise ObserverError("invalid_prior")
        if type(meta["status_freshness_seconds"]) is not int or type(meta["evidence_max_age_seconds"]) is not int or meta["status_freshness_seconds"] != FRESHNESS_SECONDS or meta["evidence_max_age_seconds"] != LOOKBACK_SECONDS:
            raise ObserverError("invalid_prior")
        if any(meta[k] != "unknown" for k in ("authority", "visibility", "current_membership", "actual_latest_outcome")):
            raise ObserverError("invalid_prior")
        generated = _time(meta["generated_at"], now)
        started = _time(meta["observation_started_at"], now)
        completed = _time(meta["observation_completed_at"], now, nullable=True)
        if started > generated or (completed is not None and (completed < started or completed > generated)):
            raise ObserverError("invalid_prior")
        if meta["observation_state"] not in {"complete", "partial", "unavailable"} or meta["reason"] not in {"none", "cap", "read_failed", "invalid_event", "conflict"}:
            raise ObserverError("invalid_prior")
        if meta["observation_state"] == "complete" and (completed is None or meta["reason"] != "none"):
            raise ObserverError("invalid_prior")
        if type(rows) is not list or len(rows) != 2 + len(RECEIPT_VIEWS):
            raise ObserverError("invalid_prior")
        for row, expected in zip(rows, [_row("attempt"), _row("inventory")] + [_row("view", v) for v in RECEIPT_VIEWS]):
            if type(row) is not dict or set(row) != ROW_KEYS or row["kind"] != expected["kind"] or row["view"] != expected["view"]:
                raise ObserverError("invalid_prior")
            if row["state"] not in {"unknown", "running", "incomplete", "ambiguous", "success", "failed", "acknowledged"} or row["reason"] not in {"none", "not_observed", "expired", "gap", "conflict", "read_failed", "empty", "scan_failed", "exception", "cap"}:
                raise ObserverError("invalid_prior")
            for key in ("started_at", "observed_at", "last_success_at"):
                _time(row[key], now, nullable=True)
            if row["storage_service_at"] is not None or row["remote_snapshot_at"] is not None:
                raise ObserverError("invalid_prior")
            for key in ("count", "last_success_count"):
                if row[key] is not None and (row["kind"] != "inventory" or type(row[key]) is not int or not 1 <= row[key] <= 2147483647):
                    raise ObserverError("invalid_prior")
            if row["sha256"] is not None and (row["kind"] != "view" or not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"])):
                raise ObserverError("invalid_prior")
            if row["attempt_id"] is not None and not re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}", str(row["attempt_id"])):
                raise ObserverError("invalid_prior")
        if type(state) is not dict or set(state) != STATE_KEYS or type(state["attempts"]) is not list or len(state["attempts"]) > MAX_ATTEMPTS:
            raise ObserverError("invalid_prior")
        watermark = _time(state["observation_high_watermark"], now, nullable=True)
        if completed != watermark:
            raise ObserverError("invalid_prior")
        seen = set()
        for attempt in state["attempts"]:
            if type(attempt) is not dict or set(attempt) != {"task_id", "events", "conflict"} or type(attempt["task_id"]) is not str or not TASK.fullmatch(attempt["task_id"]) or type(attempt["conflict"]) is not bool:
                raise ObserverError("invalid_prior")
            if type(attempt["events"]) is not list or not 1 <= len(attempt["events"]) <= MAX_SEQUENCE:
                raise ObserverError("invalid_prior")
            identity = None
            seqs = []
            for event in attempt["events"]:
                canonical = validate_event(event, now=now)
                if canonical is None or canonical != event or event["tier"] != tier:
                    raise ObserverError("invalid_prior")
                if identity is None:
                    identity = _identity(event)
                if identity != _identity(event):
                    raise ObserverError("invalid_prior")
                seqs.append(event["sequence"])
            binding = (identity, attempt["task_id"])
            if binding in seen or seqs != sorted(set(seqs)):
                raise ObserverError("invalid_prior")
            seen.add(binding)
        inventory = state["last_inventory_success"]
        view_cache = state["last_view_success"]
        if type(view_cache) is not dict or set(view_cache) - set(RECEIPT_VIEWS):
            raise ObserverError("invalid_prior")
        if inventory is not None and (validate_event(inventory, now=now) is None or inventory["event"] != "inventory_result" or inventory["payload"]["state"] != "success" or inventory["tier"] != tier):
            raise ObserverError("invalid_prior")
        for view, event in view_cache.items():
            if validate_event(event, now=now) is None or event["event"] != "view_write_result" or event["payload"]["state"] != "acknowledged" or event["payload"]["view"] != view or event["tier"] != tier:
                raise ObserverError("invalid_prior")
        # Caches deliberately aren't independent evidence. Unsupported references
        # are discarded during reduction rather than trusted as replay records.
        return copy.deepcopy(value)
    except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
        raise ObserverError("invalid_prior") from None


def _latest(candidates):
    if not candidates:
        return None, False
    latest_start = max(parse_timestamp(e["started_at"]) for e in candidates)
    latest = [e for e in candidates if parse_timestamp(e["started_at"]) == latest_start]
    if len({_identity(e) for e in latest}) != 1:
        return None, True
    return max(latest, key=lambda e: e["sequence"]), False


def reduce_projections(records, priors, *, now, observation_started_at=None,
                       observation_completed_at=None, observation_state="complete", reason="none"):
    """Merge all four tiers before deriving revocable success references."""
    start = observation_started_at or now - timedelta(seconds=LOOKBACK_SECONDS)
    completed = observation_completed_at if observation_completed_at is not None else (now if observation_state != "unavailable" else None)
    groups = {}
    trusted_refs = set()
    for tier, prior in priors.items():
        if prior is None:
            continue
        validated = validate_projection(prior, tier, now)
        for attempt in validated["_state"]["attempts"]:
            key = (*_identity(attempt["events"][0]), attempt["task_id"])
            groups[key] = copy.deepcopy(attempt)
            prefix, integrity = _legal_prefix(attempt)
            if integrity != "conflict":
                cached = [validated["_state"]["last_inventory_success"], *validated["_state"]["last_view_success"].values()]
                for event in prefix:
                    if validated["meta"]["observation_state"] == "complete" or any(event == c for c in cached):
                        trusted_refs.add(_event_ref(event))
    invalid = False
    if len(records) > MAX_RECORDS:
        raise ObserverError("state_cap")
    for record in records:
        if type(record) is not dict:
            invalid = True
            continue
        stream = record.get("logStreamName")
        match = STREAM.fullmatch(stream) if isinstance(stream, str) else None
        raw = record.get("message")
        event = parse_event(raw, now=now) if isinstance(raw, (str, bytes)) else None
        if match is None or event is None or event["tier"] != match[1]:
            invalid = True
            continue
        key = (*_identity(event), match[2])
        attempt = groups.setdefault(key, {"task_id": match[2], "events": [], "conflict": False})
        same = next((e for e in attempt["events"] if e["sequence"] == event["sequence"]), None)
        if same is not None:
            if same != event:
                attempt["conflict"] = True
        else:
            attempt["events"].append(event)
            attempt["events"].sort(key=lambda e: e["sequence"])
    # A UUID is one task/start/tier binding, globally, not one per status key.
    bindings = {}
    for key, attempt in groups.items():
        bindings.setdefault(key[0], []).append(key)
    for keys in bindings.values():
        if len(keys) > 1:
            for key in keys:
                groups[key]["conflict"] = True
    cutoff = now - timedelta(seconds=LOOKBACK_SECONDS)
    groups = {key: a for key, a in groups.items() if parse_timestamp(a["events"][0]["started_at"]) >= cutoff}
    for tier in TIERS:
        if sum(k[1] == tier for k in groups) > MAX_ATTEMPTS:
            # No truncated success: retain remote state rather than discard
            # conflict/support evidence to fit the projection.
            raise ObserverError("state_cap")
    has_conflict = any(a["conflict"] or _legal_prefix(a)[1] == "conflict" for a in groups.values())
    effective_state, effective_reason = observation_state, reason
    if has_conflict:
        effective_state, effective_reason = "partial", "conflict"
    elif invalid:
        effective_state, effective_reason = "partial", "invalid_event"
    allow_new = observation_state == "complete" and not invalid
    results = {}
    for tier in TIERS:
        attempts = sorted([a for k, a in groups.items() if k[1] == tier], key=lambda a: (parse_timestamp(a["events"][0]["started_at"]), a["task_id"]))
        valid = []
        successes = []
        for attempt in attempts:
            prefix, integrity = _legal_prefix(attempt)
            if integrity == "conflict":
                attempt["conflict"] = True
            valid.extend(prefix)
            for event in prefix:
                if allow_new or _event_ref(event) in trusted_refs:
                    if event["event"] == "inventory_result" and event["payload"]["state"] == "success":
                        successes.append(event)
                    elif event["event"] == "view_write_result" and event["payload"]["state"] == "acknowledged":
                        successes.append(event)
        inventory_success, _ = _latest([e for e in successes if e["event"] == "inventory_result"])
        view_success = {}
        for view in RECEIPT_VIEWS:
            candidate, _ = _latest([e for e in successes if e["event"] == "view_write_result" and e["payload"]["view"] == view])
            if candidate is not None:
                view_success[view] = candidate
        rows = [_row("attempt"), _row("inventory")] + [_row("view", view) for view in RECEIPT_VIEWS]
        if attempts:
            latest_start = max(parse_timestamp(a["events"][0]["started_at"]) for a in attempts)
            newest = [a for a in attempts if parse_timestamp(a["events"][0]["started_at"]) == latest_start]
            chosen = newest[0]
            prefix, integrity = _legal_prefix(chosen)
            first = chosen["events"][0]
            # Concurrent incompatible traces do not establish a newest outcome.
            overlaps = [a for a in attempts if a is not chosen and parse_timestamp(a["events"][0]["started_at"]) < latest_start and
                        (not _legal_prefix(a)[0] or _legal_prefix(a)[0][-1]["event"] != "attempt_finished" or parse_timestamp(_legal_prefix(a)[0][-1]["at"]) >= latest_start) and
                        parse_timestamp(a["events"][0]["started_at"]) + timedelta(seconds=(a["events"][0]["payload"].get("deadline_seconds", 3600) + 300)) >= latest_start]
            row = rows[0]
            row.update(attempt_id=first["attempt_id"], started_at=first["started_at"], observed_at=chosen["events"][-1]["at"])
            if len(newest) > 1 or overlaps or integrity == "conflict":
                row.update(state="ambiguous", reason="conflict")
            elif integrity == "gap":
                row.update(state="incomplete", reason="gap")
            elif prefix and prefix[-1]["event"] == "attempt_finished":
                terminal = prefix[-1]
                if terminal["payload"]["state"] == "success" and (effective_state != "complete"):
                    row.update(state="incomplete", reason="cap" if effective_reason == "cap" else "gap")
                else:
                    row.update(state=terminal["payload"]["state"], reason=terminal["payload"]["reason"])
            else:
                deadline = first["payload"].get("deadline_seconds", 0) if first["event"] == "attempt_started" else 0
                expired = now > parse_timestamp(first["started_at"]) + timedelta(seconds=deadline + 300)
                row.update(state="incomplete" if expired else "running", reason="expired" if expired else "none")
            current_inventory = next((e for e in prefix if e["event"] == "inventory_result"), None)
            if current_inventory:
                rows[1].update(attempt_id=current_inventory["attempt_id"], started_at=current_inventory["started_at"], observed_at=current_inventory["at"], state=current_inventory["payload"]["state"], reason=current_inventory["payload"]["reason"], count=current_inventory["payload"]["count"])
                if rows[1]["state"] == "success" and not (allow_new or _event_ref(current_inventory) in trusted_refs):
                    rows[1].update(state="unknown", reason="cap" if effective_reason == "cap" else "gap", count=None)
            elif integrity == "conflict":
                rows[1].update(state="unknown", reason="conflict")
            if len(newest) > 1 or overlaps:
                rows[1] = _row("inventory")
                rows[1].update(state="ambiguous", reason="conflict")
        if inventory_success:
            rows[1].update(last_success_at=inventory_success["at"], last_success_count=inventory_success["payload"]["count"])
        for row, view in zip(rows[2:], RECEIPT_VIEWS):
            all_events = [e for a in attempts for e in a["events"] if e["event"] == "view_write_result" and e["payload"]["view"] == view]
            candidate, ambiguous = _latest(all_events)
            if ambiguous:
                row.update(state="ambiguous", reason="conflict")
            elif candidate is not None:
                supporting = next(a for a in attempts if candidate in a["events"])
                prefix, integrity = _legal_prefix(supporting)
                row.update(attempt_id=candidate["attempt_id"], started_at=candidate["started_at"], observed_at=candidate["at"])
                if candidate not in prefix or integrity == "conflict":
                    row.update(state="unknown", reason="conflict" if integrity == "conflict" else "gap")
                elif candidate["payload"]["state"] == "acknowledged" and not (allow_new or _event_ref(candidate) in trusted_refs):
                    row.update(state="unknown", reason="cap" if effective_reason == "cap" else "gap")
                else:
                    row.update(state=candidate["payload"]["state"], reason="none" if candidate["payload"]["state"] == "acknowledged" else "read_failed", sha256=candidate["payload"]["sha256"])
            if view in view_success:
                row["last_success_at"] = view_success[view]["at"]
        selected_start, selected_completed, selected_state, selected_reason = start, completed, effective_state, effective_reason
        prior = priors.get(tier)
        if prior is not None:
            old_end = parse_timestamp(prior["_state"]["observation_high_watermark"])
            if old_end is not None and (selected_completed is None or old_end > selected_completed):
                selected_start = parse_timestamp(prior["meta"]["observation_started_at"])
                selected_completed = old_end
                selected_state = prior["meta"]["observation_state"]
                selected_reason = prior["meta"]["reason"]
                if has_conflict or invalid:
                    selected_state, selected_reason = "partial", "conflict" if has_conflict else "invalid_event"
        # Preserve a newer writer's admitted clock label during a slower-clock CAS merge.
        # Otherwise the carried interval can end after generated_at and our next read rejects it.
        generated = now if prior is None else max(now, parse_timestamp(prior["meta"]["generated_at"]))
        projection = {"meta": dict(version=1, tier=tier, generated_at=stamp(generated), observation_started_at=stamp(selected_start), observation_completed_at=stamp(selected_completed) if selected_completed else None,
                                   observation_state=selected_state, reason=selected_reason, status_freshness_seconds=FRESHNESS_SECONDS, evidence_max_age_seconds=LOOKBACK_SECONDS,
                                   authority="unknown", visibility="unknown", current_membership="unknown", actual_latest_outcome="unknown"),
                      "rows": rows, "_state": dict(attempts=attempts, last_inventory_success=inventory_success, last_view_success=view_success,
                                                 observation_high_watermark=stamp(selected_completed) if selected_completed else None)}
        if len(encode(projection)) > MAX_OBJECT_BYTES:
            raise ObserverError("state_cap")
        results[tier] = projection
    return results


@dataclass
class CommandResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    failure: str | None = None


class Aws:
    """CLI process edge; bounded pipes and deadline, never a shell."""
    def __init__(self, region, deadline):
        self.region, self.deadline = region, deadline

    def call(self, service, operation, arguments):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return CommandResult(1, b"", b"", "deadline")
        argv = ["aws", "--region", self.region, "--no-cli-pager", "--no-cli-auto-prompt", "--cli-connect-timeout", "5", "--cli-read-timeout", "20", "--output", "json", service, operation, *arguments]
        env = dict(os.environ, AWS_MAX_ATTEMPTS="1", AWS_PAGER="", AWS_CLI_AUTO_PROMPT="off")
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        except OSError:
            return CommandResult(1, b"", b"", "read_failed")
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, "stdout")
        selector.register(process.stderr, selectors.EVENT_READ, "stderr")
        stop_at = time.monotonic() + min(20, remaining)
        failure = None
        try:
            while selector.get_map():
                wait = stop_at - time.monotonic()
                if wait <= 0:
                    failure = "deadline"
                    break
                for key, _ in selector.select(min(wait, 0.1)):
                    data = os.read(key.fd, 65536)
                    if not data:
                        selector.unregister(key.fileobj)
                        continue
                    if sum(len(b) for b in buffers.values()) + len(data) > MAX_RESPONSE_BYTES:
                        failure = "cap"
                        break
                    buffers[key.data].extend(data)
                if service == "s3api" and operation == "get-object":
                    try:
                        if Path(arguments[-1]).stat().st_size > MAX_OBJECT_BYTES:
                            failure = "cap"
                    except FileNotFoundError:
                        pass
                if failure:
                    break
            if failure:
                process.kill()
            try:
                rc = process.wait(timeout=max(0.01, min(1, stop_at - time.monotonic())))
            except subprocess.TimeoutExpired:
                process.kill()
                rc = process.wait(timeout=1)
                failure = "deadline"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=1)
            selector.close()
            process.stdout.close()
            process.stderr.close()
        return CommandResult(rc, bytes(buffers["stdout"]), bytes(buffers["stderr"]), failure)


# Match exact AWS service error codes, never classify arbitrary error prose.
ERROR_CODE = re.compile(rb"An error occurred \(([^()\r\n]{1,80})\) when calling the (GetObject|PutObject) operation:")


def _code(result, operation):
    if result.failure:
        return None
    match = ERROR_CODE.search(result.stderr)
    return match[1].decode("ascii", "replace") if match and match[2].decode() == operation else None


@dataclass
class Prior:
    state: str
    projection: dict | None = None
    etag: str | None = None
    raw: bytes | None = None


def read_prior(aws, bucket, tier, now, directory):
    target = Path(directory) / f"get-{tier}.json"
    target.touch(mode=0o600, exist_ok=True)
    os.chmod(target, 0o600)
    result = aws.call("s3api", "get-object", ["--bucket", bucket, "--key", f"views/outcomes/{tier}.json", str(target)])
    if result.returncode != 0 or result.failure:
        code = _code(result, "GetObject")
        if code == "NoSuchKey":
            return Prior("missing")
        if code in {"AccessDenied", "403"}:
            return Prior("existence_unknown")
        return Prior("failed")
    try:
        metadata = strict_json(result.stdout)
        etag = metadata.get("ETag")
        if not isinstance(etag, str) or not 1 <= len(etag) <= 256 or any(ord(c) < 32 for c in etag):
            raise ValueError("etag")
        with target.open("rb") as handle:
            raw = handle.read(MAX_OBJECT_BYTES + 1)
        if len(raw) > MAX_OBJECT_BYTES:
            raise ValueError("cap")
        projection = validate_projection(strict_json(raw), tier, now)
        return Prior("present", projection, etag, raw)
    except (OSError, ValueError, TypeError, AttributeError, ObserverError, RecursionError):
        return Prior("failed")


def query(aws, log_group, now):
    request = dict(logGroupName=log_group, startTime=int((now - timedelta(seconds=LOOKBACK_SECONDS)).timestamp() * 1000),
                   endTime=int(now.timestamp() * 1000), filterPattern='{ $.kind = "' + EVENT_KIND + '" }', limit=10000)
    records, tokens, event_ids = [], set(), set()
    total_bytes = 0
    for _ in range(MAX_PAGES):
        result = aws.call("logs", "filter-log-events", ["--no-paginate", "--cli-input-json", json.dumps(request, separators=(",", ":"))])
        total_bytes += len(result.stdout)
        if result.failure or result.returncode != 0:
            return records, "partial" if records else "unavailable", "cap" if result.failure == "cap" else "read_failed"
        if total_bytes > MAX_QUERY_BYTES:
            return records, "partial", "cap"
        try:
            page = strict_json(result.stdout)
            events = page["events"]
            if type(events) is not list:
                raise ValueError("events")
            for record in events:
                if type(record) is not dict:
                    raise ValueError("record")
                event_id = record.get("eventId")
                if event_id is not None:
                    if not isinstance(event_id, str) or len(event_id) > 1024:
                        raise ValueError("event_id")
                    # Provider duplicates still reach sequence conflict detection
                    # if the same eventId unexpectedly carries changed bytes.
                    fingerprint = hashlib.sha256(encode(record)).digest()
                    key = (event_id, fingerprint)
                    if key in event_ids:
                        continue
                    event_ids.add(key)
                if len(records) >= MAX_RECORDS:
                    return records, "partial", "cap"
                records.append({"logStreamName": record.get("logStreamName"), "message": record.get("message")})
            token = page.get("nextToken")
            if token is None:
                return records, "complete", "none"
            if not isinstance(token, str) or not 1 <= len(token) <= 1024 or token in tokens:
                return records, "partial", "cap"
            tokens.add(token)
            request["nextToken"] = token
        except (ValueError, TypeError, KeyError, RecursionError):
            return records, "partial" if records else "unavailable", "read_failed"
    return records, "partial", "cap"


def publish(aws, bucket, tier, current, records, priors, now, observation, directory):
    """At most three conditional mutations, remerging on every CAS conflict."""
    initialized = False
    for _ in range(3):
        if current.state == "failed":
            return False, "prior_read_failed"
        if current.state == "existence_unknown":
            print("prior_read_denied")
        if current.state == "present":
            priors[tier] = current.projection
        elif initialized:
            return False, "prior_read_failed"
        else:
            priors.pop(tier, None)
        try:
            projection = reduce_projections(records, priors, now=now, **observation)[tier]
        except ObserverError:
            return False, "state_cap"
        raw = encode(projection)
        body = Path(directory) / f"put-{tier}.json"
        body.write_bytes(raw)
        os.chmod(body, 0o600)
        create = current.state != "present"
        args = ["--bucket", bucket, "--key", f"views/outcomes/{tier}.json", "--body", str(body), "--content-type", "application/json"]
        args += ["--if-none-match", "*"] if create else ["--if-match", current.etag]
        result = aws.call("s3api", "put-object", args)
        if result.returncode == 0 and result.failure is None:
            priors[tier] = projection
            if create:
                verified = read_prior(aws, bucket, tier, now, directory)
                if verified.state != "present" or hashlib.sha256(verified.raw).digest() != hashlib.sha256(raw).digest():
                    return False, "created_but_readback_unverified"
            return True, "published"
        code = _code(result, "PutObject")
        if code not in {"PreconditionFailed", "ConditionalRequestConflict", "412", "409"}:
            return False, "write_failed"
        initialized = initialized or create
        current = read_prior(aws, bucket, tier, now, directory)
        if current.state != "present":
            # Bootstrap collision permits only a readable current object.
            return False, "prior_read_denied" if current.state == "existence_unknown" else "prior_read_failed"
    return False, "write_conflict"


def _fixture(args):
    try:
        with Path(args.fixture).open("rb") as handle:
            raw = handle.read(MAX_QUERY_BYTES + 1)
        if len(raw) > MAX_QUERY_BYTES:
            raise ObserverError("fixture_cap")
        fixture = strict_json(raw)
        if type(fixture) is not dict or set(fixture) - {"events", "priors", "now", "observation_state", "reason"}:
            raise ObserverError("invalid_fixture")
        now = parse_timestamp(fixture.get("now")) if "now" in fixture else datetime.now(timezone.utc)
        if now is None or type(fixture.get("events")) is not list or type(fixture.get("priors", {})) is not dict or set(fixture.get("priors", {})) - set(TIERS):
            raise ObserverError("invalid_fixture")
        state = fixture.get("observation_state", "complete")
        reason = fixture.get("reason", "none")
        if state not in {"complete", "partial", "unavailable"} or reason not in {"none", "cap", "read_failed", "invalid_event", "conflict"}:
            raise ObserverError("invalid_fixture")
        projections = reduce_projections(fixture["events"], fixture.get("priors", {}), now=now, observation_state=state, reason=reason)
        directory = Path(args.output_dir)
        directory.mkdir(mode=0o700, parents=False, exist_ok=False)
        for tier, projection in projections.items():
            destination = directory / f"{tier}.json"
            with destination.open("xb") as handle:
                os.chmod(destination, 0o600)
                handle.write(encode(projection))
        print("fixture_rendered")
        return 0
    except (ObserverError, OSError, ValueError, TypeError, RecursionError):
        print("fixture_failed")
        return 1


def _main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bucket")
    parser.add_argument("--region")
    parser.add_argument("--log-group")
    parser.add_argument("--deadline-seconds", type=int, default=180)
    parser.add_argument("--fixture")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)
    if not 1 <= args.deadline_seconds <= 180:
        parser.error("deadline must be between 1 and 180 seconds")
    if args.fixture or args.output_dir:
        if not (args.fixture and args.output_dir) or any((args.bucket, args.region, args.log_group)):
            parser.error("fixture mode requires fixture/output-dir and excludes production arguments")
        return _fixture(args)
    if not all((args.bucket, args.region, args.log_group)):
        parser.error("production requires bucket, region and log-group")
    if not verified_ecs_runtime():
        print("runtime_identity_unverified")
        return 1
    now = datetime.now(timezone.utc)
    aws = Aws(args.region, time.monotonic() + args.deadline_seconds)
    records, state, reason = query(aws, args.log_group, now)
    end = now if state != "unavailable" else None
    observation = dict(observation_started_at=now - timedelta(seconds=LOOKBACK_SECONDS), observation_completed_at=end, observation_state=state, reason=reason)
    with tempfile.TemporaryDirectory(prefix="gcinsight-observer-") as directory:
        current = {tier: read_prior(aws, args.bucket, tier, now, directory) for tier in TIERS}
        priors = {tier: value.projection for tier, value in current.items() if value.state == "present"}
        if any(value.state != "present" for value in current.values()) and state == "complete":
            observation.update(observation_state="partial", reason="read_failed")
        results = []
        for tier in TIERS:
            success, diagnostic = publish(aws, args.bucket, tier, current[tier], records, priors, now, observation, directory)
            print(f"observer_{tier}_{diagnostic}")
            results.append(success)
    return 0 if all(results) else 1


def main(argv=None):
    try:
        return _main(argv)
    except Exception:
        print("observer_failed")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
