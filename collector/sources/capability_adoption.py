"""Org capability usage from the write stack's provisioned ``grafanacloud-usage`` datasource.

This source exists because GCI-0019 needs more than a panel: a durable named opportunity register and
bounded gap series that can drive outreach and track whether it closes. It is deliberately queried
through the write stack only. The ordinary per-stack readers retain query access to usage-insights and
cannot query this datasource.

Legacy rate-shaped numerators and denominators use the same explicit 24-hour window. Optional
footprints carry their own windows and availability; their failure cannot invalidate legacy evidence.
Only live stack ids and numeric values survive parsing; other labels and upstream details are dropped.
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
EMPTY_RESPONSE = "empty_response"
NO_VERIFIED_STACK_SOURCE = "no_verified_stack_source"


def _windowed(metric: str) -> str:
    return f"max_over_time(sum by(stack_id)({metric})[{WINDOW}:5m])"


QUERIES: Mapping[str, str] = {
    "metrics": _windowed("grafanacloud_instance_active_series"),
    "traces": _windowed("grafanacloud_traces_instance_bytes_received_per_second"),
    "span_metrics": _windowed("grafanacloud_instance_active_spanmetrics_series"),
    "service_graphs": _windowed("grafanacloud_instance_active_service_graph_series"),
    "native_histograms": _windowed("grafanacloud_instance_active_native_histogram_series"),
    "exemplars": _windowed("grafanacloud_instance_exemplars_per_second"),
    # A vendor-documented gauge of alert groups by state, not a cumulative event counter.
    # Presence identifies the reporting population; a positive level is not current-period activity.
    "irm_oncall": "sum by(stack_id)(grafanacloud_oncall_instance_alert_groups_total)",
    # Current billing-period cumulative usage, not a momentary rate.
    "k6": "sum by(stack_id)(grafanacloud_k6_stack_virtual_user_hours_usage)",
    "frontend_observability": _windowed(
        "grafanacloud_frontend_observability_instance_sessions_per_second"
    ),
    # A 24h maximum of the reporting stack's observations, not product/API inventory,
    # consumer activity or human adoption. Census name presence does not verify vendor
    # units or producer windows. Empty vectors remain empty, never defaulted to zero.
    "synthetic_monitoring": _windowed("grafanacloud_sm_billable_check_executions_per_second"),
    "kubernetes": _windowed("grafanacloud_instance_active_kube_pod_info_series"),
    "knowledge_graph": _windowed("grafanacloud_asserts_instance_active_entities"),
    "pdc": _windowed("grafanacloud_grafana_pdc_connected_agents"),
}

RATE_QUERIES = frozenset({
    "metrics", "traces", "span_metrics", "service_graphs", "native_histograms",
    "exemplars", "frontend_observability", "synthetic_monitoring",
})


FOOTPRINT_QUERIES: Mapping[str, str] = {
    "adaptive_traces": _windowed(
        "grafanacloud_traces_instance_adaptivetraces_bytes_received_per_second"
    ),
    "app_observability": _windowed("grafanacloud_app_observability_service_entity_count"),
    "agent_observability": "max_over_time(sum by(stack_id)("
        "grafanacloud_agent_observability_instance_generation_items_per_second)[30d:5m])",
    "assistant_org_users": "sum(grafanacloud_org_assistant_users)",
}

# Basis names describe measurements, not adoption, accumulated volume or human activity.
FOOTPRINT_BASIS: Mapping[str, str] = {
    "adaptive_traces": "maximum_bytes_per_second",
    "app_observability": "maximum_service_entity_count",
    "agent_observability": "maximum_generation_items_per_second",
    "assistant_org_users": "current_billing_period_org_gauge",
    "db_observability": "per_stack_unknown",
}


class AdoptionSourceError(ValueError):
    pass


def _vector(body: Any) -> list[Any]:
    if not isinstance(body, Mapping) or body.get("status") != "success":
        raise AdoptionSourceError("query did not return success")
    data = body.get("data")
    if not isinstance(data, Mapping) or data.get("resultType") != "vector":
        raise AdoptionSourceError("query did not return a vector")
    result = data.get("result")
    if not isinstance(result, list):
        raise AdoptionSourceError("query result is not a list")
    return result


def _sample(row: Any) -> float:
    if not isinstance(row, Mapping) or not isinstance(row.get("metric"), Mapping):
        raise AdoptionSourceError("query row is malformed")
    value = row.get("value")
    if not isinstance(value, list) or len(value) != 2:
        raise AdoptionSourceError("query row lacks value")
    if isinstance(value[1], bool) or not isinstance(value[1], (str, int, float)):
        raise AdoptionSourceError("query value is not numeric")
    try:
        parsed = float(value[1])
    except (TypeError, ValueError, OverflowError) as exc:
        raise AdoptionSourceError("query value is not numeric") from exc
    if not math.isfinite(parsed) or parsed < 0:
        raise AdoptionSourceError("query value is negative or non-finite")
    return parsed


def _values(body: Any) -> dict[str, float]:
    out: dict[str, float] = {}
    for row in _vector(body):
        if not isinstance(row, Mapping) or not isinstance(row.get("metric"), Mapping):
            raise AdoptionSourceError("query row is malformed")
        stack_id = row["metric"].get("stack_id")
        if not isinstance(stack_id, str) or not stack_id:
            raise AdoptionSourceError("query row lacks stack_id")
        parsed = _sample(row)
        if stack_id in out:
            raise AdoptionSourceError("query returned duplicate stack_id")
        out[stack_id] = parsed
    return out


def unavailable(reason: str, detail: str = "") -> dict[str, Any]:
    return {"available": False, "reason": reason, "detail": detail}


def _footprint_metadata(now: dt.datetime) -> dict[str, dict[str, Any]]:
    out = {}
    for name, basis in FOOTPRINT_BASIS.items():
        days = 30 if name == "agent_observability" else 1
        window: str | None = "30d" if days == 30 else WINDOW
        start: str | None = (now - dt.timedelta(days=days)).isoformat()
        end: str | None = now.isoformat()
        if name == "assistant_org_users":
            window, start = "service_default_lookback_unknown", None
        elif name == "db_observability":
            window, start, end = None, None, None
        out[name] = {"basis": basis, "window": window, "window_start": start, "window_end": end}
    return out


def _footprint(
    client: ReadOnlyClient, endpoint: str, token: str, now: dt.datetime, live_ids: set[str],
) -> dict[str, Any]:
    out = _footprint_metadata(now)
    out["db_observability"].update(available=False, reason=NO_VERIFIED_STACK_SOURCE)
    for name, expression in FOOTPRINT_QUERIES.items():
        entry = out[name]
        try:
            response = client.get(
                endpoint, params={"query": expression, "time": str(int(now.timestamp()))},
                bearer=token,
            )
        except RuntimeError:
            entry.update(available=False, reason=TRANSPORT_ERROR)
            continue
        if response.status != 200:
            entry.update(available=False, reason=HTTP_ERROR)
            continue
        try:
            body = response.json()
            if name == "assistant_org_users":
                rows = _vector(body)
                if not rows:
                    entry.update(available=False, reason=EMPTY_RESPONSE)
                    continue
                if len(rows) != 1:
                    raise AdoptionSourceError("org sum did not return exactly one row")
                measured = {"value": _sample(rows[0])}
            else:
                values = {key: value for key, value in _values(body).items() if key in live_ids}
                if not values:
                    entry.update(available=False, reason=EMPTY_RESPONSE)
                    continue
                measured = {"values": values}
        except ValueError:
            entry.update(available=False, reason=MALFORMED_RESPONSE)
            continue
        entry.update(available=True, **measured)
    return out


def _legacy(
    client: ReadOnlyClient, endpoint: str, token: str, now: dt.datetime, live_ids: set[str],
) -> dict[str, Any]:
    values: dict[str, dict[str, float]] = {}
    for name, expression in QUERIES.items():
        try:
            response = client.get(
                endpoint,
                params={"query": expression, "time": str(int(now.timestamp()))},
                bearer=token,
            )
        except RuntimeError:
            return unavailable(TRANSPORT_ERROR, f"{name}: transport error")
        if response.status != 200:
            return unavailable(HTTP_ERROR, f"{name}: HTTP {response.status}")
        try:
            values[name] = {
                key: value for key, value in _values(response.json()).items() if key in live_ids
            }
        except ValueError:
            return unavailable(MALFORMED_RESPONSE, f"{name}: malformed response")
    return {
        "available": True,
        "window_start": (now - dt.timedelta(hours=24)).isoformat(),
        "window_end": now.isoformat(),
        "values": values,
    }


def probe(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    write_stack: str,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Query through the live write stack's existing grant; optional failures stay independent."""
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=dt.timezone.utc)

    def missing(reason: str, detail: str) -> dict[str, Any]:
        footprint = _footprint_metadata(now)
        for name, entry in footprint.items():
            entry.update(available=False, reason=NO_VERIFIED_STACK_SOURCE
                         if name == "db_observability" else reason)
        return {**unavailable(reason, detail), "footprint": footprint}

    stack = next(
        (item for item in stacks
         if item.get("status") != "paused" and str(item.get("slug") or "") == write_stack),
        None,
    )
    if stack is None:
        return missing(WRITE_STACK_MISSING, "write stack is absent from live inventory")
    base, url_error = validated_base_url(stack)
    if url_error:
        return missing(INVALID_URL, "invalid inventory url")
    token = str((credentials.get(write_stack) or {}).get("token") or "")
    if not token:
        return missing(NO_CREDENTIAL, "write stack has no stored reader credential")

    live_ids = {str(item["id"]) for item in stacks if item.get("id") is not None}
    endpoint = f"{str(base).rstrip('/')}/api/datasources/proxy/uid/{DS_UID}/api/v1/query"
    legacy = _legacy(client, endpoint, token, now, live_ids)
    return {**legacy, "footprint": _footprint(client, endpoint, token, now, live_ids)}
