"""Configured IRM integration count from the one approved projected GET route.

The credential can reach secret-bearing configuration; this source never does.
Opaque IDs and activity counters are transient and discarded at this boundary.
"""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/plugins/grafana-irm-app/resources/alert_receive_channels/counters/"
MAX_INTEGRATIONS = 100_000
COUNTERS = frozenset({"alerts_count", "alert_groups_count"})


def fetch_irm_integrations(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    if not reader:
        return {"available": False, "reason": "no_credential"}
    try:
        response = client.get(base + PATH, bearer=reader, guarded=True)
        if response.status != 200:
            return {"available": False, "reason": "unreadable"}
        body = response.json()
        if not isinstance(body, dict) or len(body) > MAX_INTEGRATIONS:
            return {"available": False, "reason": "invalid_response"}
        for value in body.values():
            if (not isinstance(value, dict) or set(value) != COUNTERS
                    or any(type(counter) is not int or counter < 0 for counter in value.values())):
                return {"available": False, "reason": "invalid_response"}
        return {"available": True, "integration_count": len(body)}
    except Exception:  # noqa: BLE001 - arbitrary upstream exception content is never emitted
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Iterate the live inventory, never the credential or response population."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_irm_integrations(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "irm_integrations: " + result["reason"])
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
