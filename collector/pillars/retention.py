"""Pillar E - effective Loki per-stream retention and request-policy gaps."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from collector.coverage import Coverage

Metrics = list[tuple[str, dict[str, str], float]]
Views = dict[str, list[dict[str, Any]]]

REQUEST_STATUSES = ("applied", "pending", "rejected")

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "risk_retention_change_requests": (
        (" Stack", "string"), ("Status", "string"), ("Requested", "string"),
        ("Processed", "string"), ("Author", "string"), ("Message", "string"),
        # Infinity has no object column type.  Non-empty JSON values infer as strings; the fallback
        # must use the same supported type when a healthy request queue is empty.
        ("PR", "number"), ("Limit", "string"), ("Opaque keys", "string"),
    ),
    "risk_retention_stream": (
        (" Stack", "string"), ("Period days", "number"), ("Priority", "number"),
        ("Selector", "string"),
    ),
    "risk_retention_policy_gaps": (
        (" Stack", "string"), ("Selector", "string"), ("Expected days", "number"),
        ("Effective days", "number"),
    ),
    "risk_retention_policy_status": (
        (" Stack", "string"), ("Selector", "string"), ("Expected days", "number"),
        ("Effective days", "number"), ("Status", "string"),
    ),
}

_PERIOD = re.compile(r"^(\d+(?:\.\d+)?)([dh])$")
_EQUALITY_MATCHER = re.compile(r'\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*=\s*("(?:\\.|[^"\\])*")\s*')


def _exact_matchers(selector: str) -> dict[str, str] | None:
    """Parse only equality selectors we can use to prove two stream sets cannot overlap."""
    if not selector.startswith("{") or not selector.endswith("}"):
        return None
    body = selector[1:-1]
    matchers: dict[str, str] = {}
    position = 0
    while position < len(body):
        match = _EQUALITY_MATCHER.match(body, position)
        if match is None or match.group(1) in matchers:
            return None
        try:
            value = json.loads(match.group(2))
        except json.JSONDecodeError:
            return None
        matchers[match.group(1)] = value
        position = match.end()
        if position == len(body):
            break
        if body[position] != ",":
            return None
        position += 1
    return matchers


def _provably_disjoint(first: str, second: str) -> bool:
    first_matchers = _exact_matchers(first)
    second_matchers = _exact_matchers(second)
    return (first_matchers is not None and second_matchers is not None
            and any(first_matchers[key] != second_matchers[key]
                    for key in first_matchers.keys() & second_matchers.keys()))


def period_days(value: Any) -> float | None:
    """Parse Loki's duration notation into days without treating malformed durations as zero."""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            amount = float(value)
        except OverflowError:
            return None
        return amount if math.isfinite(amount) and amount >= 0 else None
    if not isinstance(value, str):
        return None
    match = _PERIOD.fullmatch(value.strip())
    if not match:
        return None
    amount = float(match.group(1))
    if not math.isfinite(amount):
        return None
    return amount if match.group(2) == "d" else amount / 24.0


def _policy_rows(expected_policy: Sequence[Mapping[str, Any]]) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    for item in expected_policy:
        selector = item.get("selector")
        minimum = period_days(item.get("minimum_period"))
        if not isinstance(selector, str) or not selector or minimum is None:
            raise ValueError("expected retention policy needs selector and an hours-or-days period")
        rows.append((selector, minimum))
    return rows


def _display_days(value: float) -> int | float:
    return int(value) if value.is_integer() else value


def _display_raw(value: Any) -> str | None:
    """Keep opaque API values intact while giving Infinity a stable scalar column."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def build(
    stacks: Sequence[Mapping[str, Any]],
    coverage: Coverage,
    loki_config: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    expected_policy: Sequence[Mapping[str, Any]] = (),
) -> tuple[Metrics, Views]:
    """Build only from the live inventory and readable source domains.

    `coverage` is deliberately accepted for the common pillar interface.  The source domains own their
    measured denominators because their credentials and routes are independent of scan coverage.
    """
    del coverage
    if loki_config is None:
        return [], {}

    metrics: Metrics = []
    change_rows: list[dict[str, Any]] = []
    stream_rows: list[dict[str, Any]] = []
    gap_rows: list[dict[str, Any]] = []
    policy_status_rows: list[dict[str, Any]] = []
    policy = _policy_rows(expected_policy)
    # An empty live inventory is unknown, not an estate with zero policy findings. Withhold the
    # configured-policy view and metrics so the last good view keeps its older timestamp.
    if policy and not stacks:
        return [], {}
    measured_limits = 0
    measured_requests = 0
    status_counts = {status: 0 for status in REQUEST_STATUSES}
    gaps: set[str] = set()
    compliant_stacks: set[str] = set()
    unreadable_stacks: set[str] = set()
    any_policy_measurement = False
    readable_requests = False
    readable_limits = False

    for stack in stacks:
        slug = str(stack.get("slug") or "")
        record = loki_config.get(slug) or {}
        limits = record.get("limits") if isinstance(record, Mapping) else None
        requests = record.get("change_requests") if isinstance(record, Mapping) else None
        requests_readable = isinstance(requests, Mapping) and bool(requests.get("available"))

        def unreadable_policy_rows() -> None:
            if policy:
                unreadable_stacks.add(slug)
            for selector, minimum in policy:
                unreadable_policy_row(selector, minimum)

        def unreadable_policy_row(selector: str, minimum: float) -> None:
            unreadable_stacks.add(slug)
            policy_status_rows.append({
                " Stack": slug, "Selector": selector,
                "Expected days": _display_days(minimum), "Effective days": None,
                "Status": "unreadable",
            })

        if requests_readable:
            measured_requests += 1
            readable_requests = True
            for request in requests.get("items") or []:
                if not isinstance(request, Mapping):
                    continue
                status = request.get("status")
                if status in status_counts:
                    status_counts[status] += 1
                change_rows.append({
                    " Stack": slug,
                    "Status": status,
                    "Requested": request.get("request_timestamp"),
                    "Processed": request.get("processed_timestamp"),
                    "Author": request.get("author"),
                    "Message": request.get("message"),
                    "PR": request.get("pr_number"),
                    "Limit": _display_raw(request.get("limit")),
                    "Opaque keys": _display_raw(request.get("opaque")),
                })

        if not isinstance(limits, Mapping) or not limits.get("available"):
            unreadable_policy_rows()
            continue
        # Omitted means the response lacked the field, unlike an explicit [] which is a measurable
        # absence of per-stream overrides.  Do not promote a missing field into a policy breach.
        if "retention_stream" not in limits:
            # A readable response can still omit the field entirely. It supplies no selector-level
            # evidence, so this stack is unreadable rather than a false breach or compliance result.
            if policy:
                unreadable_policy_rows()
            continue
        raw_streams = limits.get("retention_stream")
        if not isinstance(raw_streams, list):
            if policy:
                unreadable_policy_rows()
            continue
        streams: list[tuple[str, float, float]] = []
        stack_stream_rows: list[dict[str, Any]] = []
        valid_streams = True
        for stream in raw_streams:
            if not isinstance(stream, Mapping):
                valid_streams = False
                continue
            selector = stream.get("selector")
            period = period_days(stream.get("period"))
            if not isinstance(selector, str) or not selector.strip() or period is None:
                valid_streams = False
                continue
            # Loki defaults an omitted priority to zero. A supplied malformed priority is unknown,
            # not zero: coercing it could hide an overlapping rule that actually wins.
            priority = stream.get("priority", 0)
            if not isinstance(priority, (int, float)) or isinstance(priority, bool):
                valid_streams = False
                continue
            try:
                numeric_priority = float(priority)
            except OverflowError:
                valid_streams = False
                continue
            if not math.isfinite(numeric_priority):
                valid_streams = False
                continue
            stack_stream_rows.append({
                " Stack": slug,
                "Period days": _display_days(period),
                "Priority": priority,
                "Selector": selector,
            })
            streams.append((selector, period, numeric_priority))

        if not valid_streams:
            unreadable_policy_rows()
            continue
        measured_limits += 1
        readable_limits = True
        stream_rows.extend(stack_stream_rows)

        if policy:
            stack_compliant = True
            for selector, minimum in policy:
                matching = [
                    (period, priority)
                    for candidate, period, priority in streams
                    if candidate == selector
                ]
                if matching:
                    highest_priority = max(priority for _period, priority in matching)
                    # Loki uses the larger priority. Equal-priority matches use the shorter period.
                    effective = min(
                        period for period, priority in matching if priority == highest_priority
                    )
                else:
                    highest_priority = None
                    effective = None
                # An exact-selector winner covers the whole expected stream set. Overlapping
                # rules at lower priority cannot govern any of it; tied rules can change the
                # period only when shorter. Unknown overlap remains unreadable if it can win.
                if any(candidate != selector
                       and (highest_priority is None or priority > highest_priority
                            or (priority == highest_priority and period < effective))
                       and not _provably_disjoint(selector, candidate)
                       for candidate, period, priority in streams):
                    unreadable_policy_row(selector, minimum)
                    stack_compliant = False
                    continue
                any_policy_measurement = True
                status = "compliant" if effective is not None and effective >= minimum else "below policy"
                policy_status_rows.append({
                    " Stack": slug, "Selector": selector,
                    "Expected days": _display_days(minimum),
                    "Effective days": _display_days(effective) if effective is not None else None,
                    "Status": status,
                })
                if effective is None or effective < minimum:
                    stack_compliant = False
                    gaps.add(slug)
                    gap_rows.append({
                        " Stack": slug,
                        "Selector": selector,
                        "Expected days": _display_days(minimum),
                        "Effective days": _display_days(effective) if effective is not None else None,
                    })
            if stack_compliant:
                compliant_stacks.add(slug)

    if readable_limits:
        metrics.append(("gcinsight_risk_retention_stacks_measured", {}, float(measured_limits)))
    if readable_requests:
        metrics.append(("gcinsight_risk_retention_change_request_stacks", {}, float(measured_requests)))
        metrics.extend(("gcinsight_risk_retention_change_requests", {"status": status},
                        float(status_counts[status])) for status in REQUEST_STATUSES)
    if policy and any_policy_measurement:
        metrics.append(("gcinsight_risk_retention_policy_gap_stacks", {}, float(len(gaps))))
    if policy and any_policy_measurement:
        metrics.append(("gcinsight_risk_retention_policy_compliant_stacks", {},
                        float(len(compliant_stacks))))
    if policy:
        metrics.append(("gcinsight_risk_retention_policy_unreadable_stacks", {},
                        float(len(unreadable_stacks))))

    views: Views = {}
    if readable_requests:
        views["risk_retention_change_requests"] = change_rows
    if readable_limits:
        views["risk_retention_stream"] = stream_rows
    if readable_limits:
        # An empty policy view is meaningful both for a configured policy with no breaches and for a
        # deployment that has intentionally configured no expectation.  It is withheld only during a
        # complete limits outage, preserving the last good view rather than clearing it.
        views["risk_retention_policy_gaps"] = gap_rows
    views["risk_retention_policy_status"] = policy_status_rows
    return metrics, views
