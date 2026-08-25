"""Daily observed-name inventory from Mimir, Loki, Tempo and Pyroscope.

Every stack is atomic: all four bounded, explicitly-windowed reads must succeed before its observed
names are available to Pillar K. A successful empty list is preserved as a measurement; a failed read
returns only closed-vocabulary failure metadata so no later composer can mistake partial coverage for
the stack's complete observed estate.
"""

from __future__ import annotations

import datetime as dt
import socket
import urllib.error
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import DeadlineExceeded, ReadOnlyClient, Response
from collector.sources import dataplane

WINDOW = dt.timedelta(hours=24)
# The endpoint is required to be bounded even though a normal tenant has far fewer distinct names.
METRIC_NAME_LIMIT = 100_000
LABEL_VALUE_LIMIT = 100_000
FAILURE_REASONS = frozenset({
    "auth", "http_429", "http_5xx", "timeout", "invalid_response", "missing_endpoint",
    "http_other", "truncated", "unknown",
})


def _failure(slug: str, signal: str, reason: str, *, http: int | None = None) -> dict[str, Any]:
    if reason not in FAILURE_REASONS:
        reason = "unknown"
    record: dict[str, Any] = {
        "slug": slug, "available": False, "signal": signal, "reason": reason,
    }
    if http is not None:
        record["http"] = http
    return record


def _http_reason(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "missing_endpoint"
    if status == 429:
        return "http_429"
    if 500 <= status <= 599:
        return "http_5xx"
    return "http_other"


def _exception_reason(exc: BaseException) -> str:
    if isinstance(exc, (DeadlineExceeded, TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, (TimeoutError, socket.timeout)):
        return "timeout"
    return "unknown"


def _strings(value: Any) -> list[str] | None:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        return None
    return sorted(set(value))


def _get_list(
    client: ReadOnlyClient,
    url: str,
    *,
    params: Mapping[str, object],
    basic: tuple[str, str],
    field: str,
) -> tuple[list[str] | None, int | None, str | None]:
    response = client.get(url, params=params, basic=basic)
    if not response.ok:
        return None, response.status, None
    try:
        body = response.json()
    except (TypeError, ValueError):
        return None, None, "invalid_response"
    if not isinstance(body, Mapping):
        return None, None, "invalid_response"
    if body.get("status") != "success":
        return None, None, "invalid_response"
    values = _strings(body.get(field))
    if values is None:
        return None, None, "invalid_response"
    limit = params.get("limit")
    # The standard response has no documented truncation field. Reaching the requested bound is
    # therefore treated conservatively as possibly incomplete; a false unknown is safer than a
    # plausible partial asset register presented as complete.
    if isinstance(limit, int) and limit > 0 and len(values) >= limit:
        return None, None, "truncated"
    return values, None, None


def _list_failure(
    slug: str, signal: str, status: int | None, reason: str | None,
) -> dict[str, Any]:
    return _failure(
        slug, signal,
        _http_reason(status) if status is not None else (reason or "invalid_response"),
        http=status,
    )


def _tempo_values(response: Response) -> list[str] | None:
    try:
        body = response.json()
    except (TypeError, ValueError):
        return None
    if not isinstance(body, Mapping) or not isinstance(body.get("tagValues"), list):
        return None
    values: list[str] = []
    for record in body["tagValues"]:
        if not isinstance(record, Mapping) or not isinstance(record.get("value"), str):
            return None
        values.append(record["value"])
    return sorted(set(values))


def _base_and_auth(
    stack: Mapping[str, Any], signal: str, url_field: str, cap: str,
) -> tuple[str, tuple[str, str]] | None:
    base = stack.get(url_field)
    if not isinstance(base, str) or not base:
        return None
    try:
        auth = dataplane.auth_for(dict(stack), signal, cap)
    except KeyError:
        return None
    return base.rstrip("/"), auth


def probe_stack(
    client: ReadOnlyClient,
    stack: Mapping[str, Any],
    cap: str,
    *,
    now: dt.datetime | None = None,
) -> dict[str, Any]:
    """Read one live stack, withholding its row unless every signal answers validly."""
    slug = str(stack.get("slug") or "")
    end = now or dt.datetime.now(dt.timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=dt.timezone.utc)
    end = end.astimezone(dt.timezone.utc)
    start = end - WINDOW
    start_seconds, end_seconds = int(start.timestamp()), int(end.timestamp())
    current_signal = "metrics"

    try:
        located = _base_and_auth(stack, "metrics", "hmInstancePromUrl", cap)
        if located is None:
            return _failure(slug, "metrics", "missing_endpoint")
        base, auth = located
        metric_names, status, reason = _get_list(
            client, f"{base}/api/prom/api/v1/label/__name__/values",
            params={"start": start_seconds, "end": end_seconds, "limit": METRIC_NAME_LIMIT},
            basic=auth, field="data",
        )
        if metric_names is None:
            return _list_failure(slug, "metrics", status, reason)

        metric_services, status, reason = _get_list(
            client, f"{base}/api/prom/api/v1/label/service_name/values",
            params={"start": start_seconds, "end": end_seconds, "limit": LABEL_VALUE_LIMIT},
            basic=auth, field="data",
        )
        if metric_services is None:
            return _list_failure(slug, "metrics", status, reason)
        slo_services, status, reason = _get_list(
            client, f"{base}/api/prom/api/v1/label/service_name/values",
            params={
                "start": start_seconds,
                "end": end_seconds,
                "limit": LABEL_VALUE_LIMIT,
                "match[]": '{grafana_slo_uuid!="",service_name!=""}',
            },
            basic=auth, field="data",
        )
        if slo_services is None:
            return _list_failure(slug, "metrics", status, reason)
        legacy_metric_services, status, reason = _get_list(
            client, f"{base}/api/prom/api/v1/label/service/values",
            params={"start": start_seconds, "end": end_seconds, "limit": LABEL_VALUE_LIMIT},
            basic=auth, field="data",
        )
        if legacy_metric_services is None:
            return _list_failure(slug, "metrics", status, reason)
        clusters, status, reason = _get_list(
            client, f"{base}/api/prom/api/v1/label/cluster/values",
            params={"start": start_seconds, "end": end_seconds, "limit": LABEL_VALUE_LIMIT},
            basic=auth, field="data",
        )
        if clusters is None:
            return _list_failure(slug, "metrics", status, reason)

        current_signal = "logs"
        located = _base_and_auth(stack, "logs", "hlInstanceUrl", cap)
        if located is None:
            return _failure(slug, "logs", "missing_endpoint")
        base, auth = located
        log_services, status, reason = _get_list(
            client, f"{base}/loki/api/v1/label/service_name/values",
            params={"start": start_seconds * 1_000_000_000, "end": end_seconds * 1_000_000_000},
            basic=auth, field="data",
        )
        if log_services is None:
            return _list_failure(slug, "logs", status, reason)

        current_signal = "traces"
        located = _base_and_auth(stack, "traces", "htInstanceUrl", cap)
        if located is None:
            return _failure(slug, "traces", "missing_endpoint")
        base, auth = located
        tempo = client.get(
            f"{base}/tempo/api/v2/search/tag/resource.service.name/values",
            params={"start": start_seconds, "end": end_seconds}, basic=auth,
        )
        if not tempo.ok:
            return _failure(slug, "traces", _http_reason(tempo.status), http=tempo.status)
        trace_services = _tempo_values(tempo)
        if trace_services is None:
            return _failure(slug, "traces", "invalid_response")

        current_signal = "profiles"
        located = _base_and_auth(stack, "profiles", "hpInstanceUrl", cap)
        if located is None:
            return _failure(slug, "profiles", "missing_endpoint")
        base, (user, _) = located
        profiles = dataplane._connect_rpc(
            f"{base}/querier.v1.QuerierService/LabelValues", user, cap,
            payload={
                "name": "service_name", "start": start_seconds * 1000, "end": end_seconds * 1000,
            },
        )
        if not isinstance(profiles, Mapping):
            return _failure(slug, "profiles", "invalid_response")
        rpc_status = profiles.get("_http")
        if isinstance(rpc_status, int):
            return _failure(slug, "profiles", _http_reason(rpc_status), http=rpc_status)
        profile_services = _strings(profiles.get("names"))
        if profile_services is None:
            return _failure(slug, "profiles", "invalid_response")
    except Exception as exc:  # noqa: BLE001 - one signal failure becomes a closed stack record
        return _failure(slug, current_signal, _exception_reason(exc))

    return {
        "slug": slug,
        "available": True,
        "window_start": start.isoformat(),
        "window_end": end.isoformat(),
        "metric_names": metric_names,
        "metric_services": metric_services,
        "slo_services": slo_services,
        "legacy_metric_services": legacy_metric_services,
        "clusters": clusters,
        "log_services": log_services,
        "trace_services": trace_services,
        "profile_services": profile_services,
    }


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    cap: str,
    *,
    concurrency: int = 12,
    now: dt.datetime | None = None,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Sweep the supplied fresh inventory; never iterate a saved per-stack payload."""
    active = [
        stack for stack in stacks
        if stack.get("slug") and stack.get("status") != "paused"
    ]
    out: dict[str, dict[str, Any]] = {}

    def one(stack: Mapping[str, Any]) -> None:
        slug = str(stack["slug"])
        record = probe_stack(client, stack, cap, now=now)
        out[slug] = record
        if not record.get("available") and on_error:
            on_error(slug, f"{record.get('signal')}: {record.get('reason')}")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(one, active))
    return out
