"""Fixed configured-report GET; all object details remain transient."""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.resource_schema import UnsafeSchema, guard_resource
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/reports"
MAX_REPORTS = 100_000


def fetch_reports(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
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
        # Only the witnessed complete bare list is supported. No wrapper/paging fallback.
        if not isinstance(body, list) or len(body) > MAX_REPORTS:
            return {"available": False, "reason": "invalid_response"}
        guard_resource(body)
        for report in body:
            if not isinstance(report, dict):
                return {"available": False, "reason": "invalid_response"}
            identity = report.get("id")
            if not ((type(identity) is int and identity > 0)
                    or (isinstance(identity, str) and identity.strip())):
                return {"available": False, "reason": "invalid_response"}
        return {"available": True, "report_count": len(body)}
    except UnsafeSchema:
        return {"available": False, "reason": "unsafe_schema"}
    except Exception:  # noqa: BLE001 - upstream exception text may contain report content
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Left-join credentials onto the fresh inventory, never the reverse."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_reports(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "reports_inventory: " + result["reason"])
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
