"""Minimized IRM alert-group count from the one witnessed default-window stats GET."""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/plugins/grafana-irm-app/resources/alertgroups/stats/"
# Count values beyond this fixed bound are unavailable rather than silently truncated.
MAX_COUNT = 999_999_999_999_999_999
_COUNT = re.compile(r"(0|[1-9][0-9]*)(\+)?\Z")


def fetch_irm_alert_groups(
    client: ReadOnlyClient, stack: Mapping[str, Any], reader: str,
) -> dict[str, Any]:
    """Read only count/relation from the exact stats route; never retain upstream content."""
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
        if not isinstance(body, dict) or set(body) != {"count"}:
            return {"available": False, "reason": "invalid_response"}
        raw_count = body["count"]
        if not isinstance(raw_count, str):
            return {"available": False, "reason": "invalid_response"}
        match = _COUNT.fullmatch(raw_count)
        if match is None or len(match.group(1)) > 18:
            return {"available": False, "reason": "invalid_response"}
        count = int(match.group(1))
        if count > MAX_COUNT:
            return {"available": False, "reason": "invalid_response"}
        return {
            "available": True,
            "alert_group_count": count,
            "relation": "at_least" if match.group(2) else "exact",
            "population": "api_default_window",
        }
    except Exception:  # noqa: BLE001 - upstream exceptions and body are never emitted
        return {"available": False, "reason": "transport_error"}


def probe_all(
    client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Left-join credentials onto live inventory; never iterate the credential population."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_irm_alert_groups(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "irm_alert_groups: " + result["reason"])
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
