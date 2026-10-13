"""Bounded private collector acknowledgements, separate from publication success proof.

Recording is best effort. The observer validates the original typed records and their sequence;
no arbitrary payload, exception or identity is carried by this interface.
"""
from __future__ import annotations

import contextlib
import contextvars
import datetime as dt
import json
import math
import re
import sys
import uuid
from typing import Any, Callable

EVENT_VERSION = 1
EVENT_KIND = 'gcinsight_outcome'
MAX_EVENT_BYTES = 2048
MAX_SEQUENCE = 16
RECEIPT_VIEWS = ('cost_summary', 'usage_summary', 'risk_summary', 'value_summary', 'coverage_summary')
TIERS = ('t1', 't2', 't3', 't4')
_COMMON = {'kind', 'version', 'event', 'attempt_id', 'tier', 'started_at', 'at',
           'sequence', 'source_revision', 'payload'}
_ACTIVE: contextvars.ContextVar[Recorder | None] = contextvars.ContextVar('outcome_recorder', default=None)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def parse_timestamp(value: Any) -> dt.datetime | None:
    if (not isinstance(value, str) or len(value) > 32
            or re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?(?:Z|\+00:00)', value) is None):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0) or not 2000 <= parsed.year <= 2100:
            return None
        return parsed
    except ValueError:
        return None


def _stamp(value: dt.datetime | None) -> str | None:
    try:
        return value.isoformat() if value is not None else None
    except Exception:
        return None


def _integer(value: Any, low: int, high: int) -> bool:
    return type(value) is int and low <= value <= high


def _interval(payload: dict, first: str, last: str, start: dt.datetime, end: dt.datetime,
              *, nullable: bool = False) -> bool:
    a, b = payload.get(first), payload.get(last)
    if nullable and a is None and b is None:
        return True
    a, b = parse_timestamp(a), parse_timestamp(b)
    return a is not None and b is not None and start <= a <= b <= end


def validate_event(value: Any, *, now: dt.datetime | None = None) -> dict | None:
    """Return an independent canonical record, or refuse the entire unsupported record."""
    try:
        if not isinstance(value, dict) or set(value) != _COMMON:
            return None
        if value['kind'] != EVENT_KIND or type(value['version']) is not int or value['version'] != EVENT_VERSION:
            return None
        if value['tier'] not in TIERS or not _integer(value['sequence'], 1, MAX_SEQUENCE):
            return None
        attempt_id = value['attempt_id']
        if not isinstance(attempt_id, str) or str(uuid.UUID(attempt_id, version=4)) != attempt_id:
            return None
        revision = value['source_revision']
        if revision is not None and (not isinstance(revision, str) or re.fullmatch('[0-9a-f]{40}', revision) is None):
            return None
        start, end = parse_timestamp(value['started_at']), parse_timestamp(value['at'])
        if start is None or end is None or start > end or end > (now or utcnow()) + dt.timedelta(seconds=300):
            return None
        payload = value['payload']
        if not isinstance(payload, dict):
            return None
        event = value['event']
        if event == 'attempt_started':
            valid = (set(payload) == {'deadline_seconds'} and value['sequence'] == 1 and start == end
                     and _integer(payload['deadline_seconds'], 1, 3600))
        elif event == 'inventory_result':
            valid = set(payload) == {'state', 'reason', 'count', 'read_started_at', 'read_completed_at'}
            state, reason, count = payload.get('state'), payload.get('reason'), payload.get('count')
            if value['tier'] == 't4' and state != 'unknown':
                return None
            if state == 'success':
                valid = valid and reason == 'none' and _integer(count, 1, 2**31 - 1) and _interval(
                    payload, 'read_started_at', 'read_completed_at', start, end)
            elif state == 'failed':
                valid = valid and reason in ('empty', 'read_failed') and count is None and _interval(
                    payload, 'read_started_at', 'read_completed_at', start, end, nullable=True)
            elif state == 'unknown':
                valid = valid and value['tier'] == 't4' and reason == 'not_observed' and count is None \
                    and payload.get('read_started_at') is None and payload.get('read_completed_at') is None
            else:
                valid = False
        elif event == 'view_write_result':
            valid = (set(payload) == {'view', 'state', 'sha256', 'request_started_at', 'request_completed_at'}
                     and payload.get('view') in RECEIPT_VIEWS and payload.get('state') in ('acknowledged', 'failed')
                     and isinstance(payload.get('sha256'), str) and re.fullmatch('[0-9a-f]{64}', payload['sha256']) is not None
                     and _interval(payload, 'request_started_at', 'request_completed_at', start, end))
        elif event == 'attempt_finished':
            state, reason, code = payload.get('state'), payload.get('reason'), payload.get('exit_code')
            valid = set(payload) == {'state', 'reason', 'exit_code'} and (
                (state == 'success' and reason == 'none' and type(code) is int and code == 0)
                or (state == 'failed' and reason == 'scan_failed' and _integer(code, 1, 3))
                or (state == 'failed' and reason == 'exception' and code is None))
        else:
            valid = False
        if not valid or (event != 'attempt_started' and value['sequence'] == 1):
            return None
        raw = json.dumps(value, separators=(',', ':'), allow_nan=False)
        if len(raw.encode('utf-8')) > MAX_EVENT_BYTES:
            return None
        return json.loads(raw)
    except (ValueError, TypeError, OverflowError, KeyError, AttributeError, RecursionError):
        return None


def parse_event(raw: str | bytes, *, now: dt.datetime | None = None) -> dict | None:
    def unique_pairs(pairs):
        result = {}
        for key, val in pairs:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = val
        return result
    try:
        if not isinstance(raw, (str, bytes)) or len(raw if isinstance(raw, bytes) else raw.encode('utf-8')) > MAX_EVENT_BYTES:
            return None
        value = json.loads(raw, object_pairs_hook=unique_pairs,
                           parse_constant=lambda value: (_ for _ in ()).throw(ValueError('nonfinite')))
        return validate_event(value, now=now)
    except (ValueError, TypeError, UnicodeError, RecursionError):
        return None


def _diagnostic() -> None:
    print('{"level":"warn","message":"outcome_recording_failed"}', file=sys.stderr)


def _emit(event: dict) -> None:
    print(json.dumps(event, separators=(',', ':'), allow_nan=False), file=sys.stderr, flush=True)


def current() -> Recorder | None:
    return _ACTIVE.get()


@contextlib.contextmanager
def recording(recorder: Recorder | None):
    token = _ACTIVE.set(recorder)
    try:
        yield recorder
    finally:
        _ACTIVE.reset(token)


class Recorder:
    def __init__(self, tier: str, deadline_seconds: int, source_revision: str | None,
                 emit: Callable[[dict], None], clock: Callable[[], dt.datetime]):
        self.tier, self.deadline_seconds, self.source_revision = tier, deadline_seconds, source_revision
        self.emit, self.clock = emit, clock
        self.attempt_id = str(uuid.uuid4())
        self.started_at = clock().isoformat()
        self.sequence = 0
        self.finished = False
        self.inventory_state: str | None = None
        self.views: set[str] = set()
        self.diagnosed = False

    def _failed(self):
        if not self.diagnosed:
            self.diagnosed = True
            try:
                _diagnostic()
            except Exception:
                pass

    @classmethod
    def start(cls, tier: str, deadline_seconds: float, source_revision: str | None = None,
              emit: Callable[[dict], None] = _emit, *, clock: Callable[[], dt.datetime] = utcnow) -> Recorder | None:
        try:
            if type(deadline_seconds) not in (int, float) or not math.isfinite(deadline_seconds) or not 0 < deadline_seconds <= 3600:
                raise ValueError('unsupported deadline')
            if source_revision is not None and (not isinstance(source_revision, str) or re.fullmatch('[0-9a-f]{40}', source_revision) is None):
                source_revision = None
            recorder = cls(tier, math.ceil(deadline_seconds), source_revision, emit, clock)
            recorder._record('attempt_started', {'deadline_seconds': recorder.deadline_seconds}, at=recorder.started_at)
            return recorder
        except Exception:
            try:
                _diagnostic()
            except Exception:
                pass
            return None

    def _record(self, event: str, payload: dict, *, at: str | None = None):
        if self.finished:
            return
        self.sequence += 1  # consume before clock, validation or sink: a failed record leaves a gap
        try:
            value = {'kind': EVENT_KIND, 'version': EVENT_VERSION, 'event': event,
                     'attempt_id': self.attempt_id, 'tier': self.tier, 'started_at': self.started_at,
                     'at': at or self.clock().isoformat(), 'sequence': self.sequence,
                     'source_revision': self.source_revision, 'payload': payload}
            valid = validate_event(value, now=self.clock())
            if valid is None:
                raise ValueError('invalid event')
            self.emit(valid)
        except Exception:
            self._failed()

    def inventory(self, state: str, *, reason: str = 'none', count: int | None = None,
                  read_started_at: dt.datetime | None = None, read_completed_at: dt.datetime | None = None):
        try:
            if self.inventory_state is not None or self.finished:
                return
            self.inventory_state = state
            self._record('inventory_result', {'state': state, 'reason': reason, 'count': count,
                         'read_started_at': _stamp(read_started_at),
                         'read_completed_at': _stamp(read_completed_at)})
        except Exception:
            self._failed()

    def view_write(self, view: str, state: str, sha256: str, *, request_started_at: dt.datetime,
                   request_completed_at: dt.datetime):
        try:
            if view not in RECEIPT_VIEWS or view in self.views or self.finished:
                return
            if self.inventory_state not in ('success', 'unknown'):
                return
            self.views.add(view)
            self._record('view_write_result', {'view': view, 'state': state, 'sha256': sha256,
                         'request_started_at': _stamp(request_started_at),
                         'request_completed_at': _stamp(request_completed_at)})
        except Exception:
            self._failed()

    def now(self) -> dt.datetime | None:
        try:
            return self.clock()
        except Exception:
            self._failed()
            return None

    def finish(self, exit_code: int | None = None, *, exception: bool = False):
        try:
            self._record('attempt_finished', {'state': 'success' if not exception and exit_code == 0 else 'failed',
                         'reason': 'exception' if exception else 'none' if exit_code == 0 else 'scan_failed',
                         'exit_code': None if exception else exit_code})
        except Exception:
            self._failed()
        finally:
            self.finished = True
