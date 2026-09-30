"""SLO definitions, not multidimensional SLI series or firing alert instances.

The deployed SLO client lists this unpaged resources route. Approved existing
basic-None readers matched a positive Admin control. No role changes are made here.
Only counts and closed enums leave this source, including on error paths.
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from collector.httpclient import ReadOnlyClient
from collector.sources.resource_schema import UnsafeSchema, guard_resource
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/plugins/grafana-slo-app/resources/v1/slo"
PROVENANCES = ("api", "asserts", "unknown")
STATUSES = ("created", "updated", "unknown")
SOURCES = ("metrics", "knowledge_graph", "unknown")
# Explicit source types only. API provenance alone says nothing about signal origin.
METRIC_TYPES = frozenset({"mimir", "prometheus"})
MAX_DEFINITIONS = 100_000


def fetch_slo_inventory(
    client: ReadOnlyClient, stack: Mapping[str, Any], reader: str,
) -> dict[str, Any] | None:
    """Return the minimized complete list projection, or unknown on an unreadable response.

    Never guess a hostname, log an upstream error body, or persist raw SLO records.
    The deployed list has no pagination contract; unexpected envelopes are rejected.
    """
    url, error = validated_base_url(stack)
    if not reader or error:
        return None
    response = client.get(url + PATH, bearer=reader, guarded=True)
    if not response.ok:
        return None
    body = guard_resource(response.json())
    if not isinstance(body, Mapping) or set(body) != {"slos"}:
        return None
    items = body["slos"]
    if (not isinstance(items, list) or len(items) > MAX_DEFINITIONS
            or not all(isinstance(item, Mapping) for item in items)):
        return None
    result = {
        "available": True,
        "count": len(items),
        "configured_alerting_count": 0,
        "provenance_counts": dict.fromkeys(PROVENANCES, 0),
        "status_counts": dict.fromkeys(STATUSES, 0),
        "source_counts": dict.fromkeys(SOURCES, 0),
    }
    for item in items:
        readonly = item.get("readOnly")
        readonly = readonly if isinstance(readonly, Mapping) else {}
        provenance = readonly.get("provenance")
        provenance = provenance if provenance in PROVENANCES else "unknown"
        result["provenance_counts"][provenance] += 1
        status = readonly.get("status")
        status = status.get("type") if isinstance(status, Mapping) else None
        status = status if status in STATUSES else "unknown"
        result["status_counts"][status] += 1
        datasource = readonly.get("sourceDatasource")
        datatype = datasource.get("type") if isinstance(datasource, Mapping) else None
        source = "unknown"
        if provenance == "asserts":
            source = "knowledge_graph"
        elif isinstance(datatype, str) and datatype in METRIC_TYPES:
            source = "metrics"
        result["source_counts"][source] += 1
        alerting = item.get("alerting")
        if isinstance(alerting, Mapping) and any(
            isinstance(alerting.get(kind), Mapping) for kind in ("fastBurn", "slowBurn")
        ):
            result["configured_alerting_count"] += 1
    return result


def probe_all(
    client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Discover from the live inventory; credential state is only a left-join lookup."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        reason = "no_credential" if not token else "unreadable"
        result = None
        if token:
            try:
                result = fetch_slo_inventory(client, stack, token)
            except UnsafeSchema:
                reason = "unsafe_schema"
            except Exception:  # noqa: BLE001 - raw exception text may contain product content
                reason = "transport_error"
        if result is None:
            result = {"available": False, "reason": reason}
            if on_error:
                on_error(slug, f"slo_inventory: {reason}")
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
