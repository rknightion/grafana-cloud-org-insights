"""Org capability usage from the write stack's provisioned ``grafanacloud-usage`` datasource.

This source exists because GCI-0019 needs more than a panel: a durable named opportunity register and
bounded gap series that can drive outreach and track whether it closes. It is deliberately queried
through the write stack only. The ordinary per-stack readers retain query access to usage-insights and
cannot query this datasource.

Every rate-shaped numerator and denominator uses the same explicit 24-hour window. The response keeps
only stack ids and numeric values; label values from usage metrics are never republished.
"""

from __future__ import annotations

import datetime as dt
import math
from collections.abc import Mapping, Sequence
from typing import Any

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

DS_UID = "grafanacloud-usage"
WINDOW = "24h"

NO_CREDENTIAL = "no_credential"
WRITE_STACK_MISSING = "write_stack_missing"
INVALID_URL = "invalid_url"
HTTP_ERROR = "http_error"
MALFORMED_RESPONSE = "malformed_response"
TRANSPORT_ERROR = "transport_error"


def _windowed(metric: str) -> str:
    return f"max_over_time(sum by(stack_id)({metric})[{WINDOW}:5m])"


QUERIES: Mapping[str, str] = {
    "metrics": _windowed("grafanacloud_instance_active_series"),
    "traces": _windowed("grafanacloud_traces_instance_bytes_received_per_second"),
    "span_metrics": _windowed("grafanacloud_instance_active_spanmetrics_series"),
    "service_graphs": _windowed("grafanacloud_instance_active_service_graph_series"),
    "native_histograms": _windowed("grafanacloud_instance_active_native_histogram_series"),
    "exemplars": _windowed("grafanacloud_instance_exemplars_per_second"),
    # A cumulative counter. Presence identifies the provisioned OnCall population; a positive value
    # identifies stacks that have actually raised an alert group.
    "irm_oncall": "sum by(stack_id)(grafanacloud_oncall_instance_alert_groups_total)",
    # Current billing-period cumulative usage, not a momentary rate.
    "k6": "sum by(stack_id)(grafanacloud_k6_stack_virtual_user_hours_usage)",
    "frontend_observability": _windowed(
        "grafanacloud_frontend_observability_instance_sessions_per_second"
    ),
}

RATE_QUERIES = frozenset({
    "metrics", "traces", "span_metrics", "service_graphs", "native_histograms",
    "exemplars", "frontend_observability",
})


class AdoptionSourceError(ValueError):
    pass


def _values(body: Any) -> dict[str, float]:
    if not isinstance(body, Mapping) or body.get("status") != "success":
        raise AdoptionSourceError("query did not return success")
    data = body.get("data")
    if not isinstance(data, Mapping) or data.get("resultType") != "vector":
        raise AdoptionSourceError("query did not return a vector")
    result = data.get("result")
    if not isinstance(result, list):
        raise AdoptionSourceError("query result is not a list")
    out: dict[str, float] = {}
    for row in result:
        if not isinstance(row, Mapping) or not isinstance(row.get("metric"), Mapping):
            raise AdoptionSourceError("query row is malformed")
        stack_id = row["metric"].get("stack_id")
        value = row.get("value")
        if not isinstance(stack_id, str) or not stack_id or not isinstance(value, list) \
                or len(value) != 2:
            raise AdoptionSourceError("query row lacks stack_id or value")
        try:
            parsed = float(value[1])
        except (TypeError, ValueError) as exc:
            raise AdoptionSourceError("query value is not numeric") from exc
        if not math.isfinite(parsed) or parsed < 0:
            raise AdoptionSourceError("query value is negative or non-finite")
        if stack_id in out:
            raise AdoptionSourceError("query returned duplicate stack_id")
        out[stack_id] = parsed
    return out


def unavailable(reason: str, detail: str = "") -> dict[str, Any]:
    return {"available": False, "reason": reason, "detail": detail}


def probe(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    write_stack: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Query once through the live write-stack record and its existing reader credential."""
    stack = next(
        (item for item in stacks
         if item.get("status") != "paused" and str(item.get("slug") or "") == write_stack),
        None,
    )
    if stack is None:
        return unavailable(WRITE_STACK_MISSING, "write stack is absent from live inventory")
    base, url_error = validated_base_url(stack)
    if url_error:
        return unavailable(INVALID_URL, str(url_error.get("detail") or "invalid inventory url"))
    token = str((credentials.get(write_stack) or {}).get("token") or "")
    if not token:
        return unavailable(NO_CREDENTIAL, "write stack has no stored reader credential")

    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)
    endpoint = f"{str(base).rstrip('/')}/api/datasources/proxy/uid/{DS_UID}/api/v1/query"
    values: dict[str, dict[str, float]] = {}
    for name, expression in QUERIES.items():
        try:
            response = client.get(
                endpoint,
                params={"query": expression, "time": str(int(now.timestamp()))},
                bearer=token,
            )
        except RuntimeError as exc:
            return unavailable(TRANSPORT_ERROR, f"{name}: {exc}")
        if not response.ok:
            return unavailable(HTTP_ERROR, f"{name}: HTTP {response.status}")
        try:
            values[name] = _values(response.json())
        except (ValueError, AdoptionSourceError) as exc:
            return unavailable(MALFORMED_RESPONSE, f"{name}: {exc}")
    return {
        "available": True,
        "window_start": (now - dt.timedelta(hours=24)).isoformat(),
        "window_end": now.isoformat(),
        "values": values,
    }
