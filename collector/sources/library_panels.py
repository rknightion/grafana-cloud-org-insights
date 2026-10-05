"""Count configured library panels; witnessed folder-wide reader coverage is required.

Effective wildcard folder coverage is checked before the fixed kind=1 collection GET.
Models, targets, creator metadata and
all other private fields remain transient, never part of the public reader result.
"""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/library-elements"
PERMISSIONS_PATH = "/api/access-control/user/permissions"
REQUIRED_PAIRS = frozenset({("library.panels:read", "folders:*"), ("folders:read", "folders:*")})
PAGE_SIZE = 100
MAX_PAGES = 1000
MAX_PANELS = 100_000


def fetch_library_panels(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    if not reader:
        return {"available": False, "reason": "no_credential"}
    seen: set[int] = set()
    total = None
    try:
        coverage = client.get(base + PERMISSIONS_PATH, bearer=reader, guarded=True)
        if coverage.status != 200:
            return {"available": False, "reason": "coverage_unavailable"}
        permissions = coverage.json()
        # This witnessed endpoint is an action -> scope-list mapping. Never accept
        # scope-blind names, scalar strings, coerced values or pseudo-folder reads.
        if not isinstance(permissions, dict) or any(
            not isinstance(action, str) or not action
            or not isinstance(scopes, list)
            or any(not isinstance(scope, str) for scope in scopes)
            for action, scopes in permissions.items()
        ):
            return {"available": False, "reason": "coverage_unavailable"}
        effective = frozenset((action, scope) for action, scopes in permissions.items() for scope in scopes)
        if not REQUIRED_PAIRS <= effective:
            return {"available": False, "reason": "coverage_unavailable"}
        for number in range(1, MAX_PAGES + 1):
            # Never follow a supplied URL or request element details.
            response = client.get(base + PATH + f"?kind=1&perPage={PAGE_SIZE}&page={number}",
                                  bearer=reader, guarded=True)
            if response.status != 200:
                return {"available": False, "reason": "unreadable"}
            body = response.json()
            result = body.get("result") if isinstance(body, dict) else None
            if not isinstance(result, dict):
                return {"available": False, "reason": "invalid_response"}
            page, per_page, current_total = (result.get(key) for key in ("page", "perPage", "totalCount"))
            elements = result.get("elements")
            if (type(page) is not int or page != number
                    or type(per_page) is not int or per_page != PAGE_SIZE
                    or type(current_total) is not int or not 0 <= current_total <= MAX_PANELS
                    or not isinstance(elements, list)):
                return {"available": False, "reason": "invalid_response"}
            if total is None:
                total = current_total
            if current_total != total or len(elements) != min(PAGE_SIZE, total - len(seen)):
                return {"available": False, "reason": "incomplete_inventory"}
            for element in elements:
                if not isinstance(element, dict):
                    return {"available": False, "reason": "invalid_response"}
                identity, kind = element.get("id"), element.get("kind")
                if type(identity) is not int or identity <= 0 or type(kind) is not int or kind != 1:
                    return {"available": False, "reason": "invalid_response"}
                if identity in seen:
                    return {"available": False, "reason": "incomplete_inventory"}
                seen.add(identity)
            if len(seen) == total:
                return {"available": True, "library_panel_count": total}
        return {"available": False, "reason": "incomplete_inventory"}
    except Exception:  # noqa: BLE001 - exception text may contain models, credentials or creator data
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Left-join credentials onto the caller's fresh inventory, never credential population."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_library_panels(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "library_panels_inventory: " + result["reason"])
        return slug, result

    selected = [stack for stack in stacks if stack.get("slug") and stack.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
