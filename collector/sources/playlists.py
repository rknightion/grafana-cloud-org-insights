"""Count-only reader for the witnessed legacy playlist collection route."""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.resource_schema import UnsafeSchema, guard_resource
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/playlists"
MAX_PLAYLISTS = 100_000
_FIELDS = frozenset({"interval", "name", "uid"})


def fetch_playlists(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
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
        # Only the witnessed complete bare array is accepted; never follow paging or fetch details.
        if not isinstance(body, list) or len(body) > MAX_PLAYLISTS:
            return {"available": False, "reason": "invalid_response"}
        guard_resource(body)
        for playlist in body:
            if not isinstance(playlist, dict) or set(playlist) != _FIELDS:
                return {"available": False, "reason": "invalid_response"}
            if any(not isinstance(playlist[field], str) for field in _FIELDS):
                return {"available": False, "reason": "invalid_response"}
        return {"available": True, "playlist_count": len(body)}
    except UnsafeSchema:
        return {"available": False, "reason": "unsafe_schema"}
    except Exception:  # noqa: BLE001 - upstream exception text may contain playlist content
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Left-join credentials onto fresh inventory; never iterate a credential population."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_playlists(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "playlists_inventory: " + result["reason"])
        return slug, result

    selected = [stack for stack in stacks if stack.get("slug") and stack.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
