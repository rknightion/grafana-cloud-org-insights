"""Count the approved bare Faro app array; discard all app details at parse."""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/plugin-proxy/grafana-kowalski-app/api-proxy/api/v1/app"
MAX_APPS = 100_000
APP_TYPES = ("web", "mobile", "unknown")


def fetch_faro_apps(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    if not reader:
        return {"available": False, "reason": "no_credential"}
    try:
        response = client.get(base + PATH, bearer=reader, guarded=True)
        if not response.ok:
            return {"available": False, "reason": "unreadable"}
        body = response.json()
        if not isinstance(body, list) or len(body) > MAX_APPS:
            return {"available": False, "reason": "invalid_response"}
        counts = dict.fromkeys(APP_TYPES, 0)
        for app in body:
            if not isinstance(app, dict):
                return {"available": False, "reason": "invalid_response"}
            kind = app.get("appType")
            if kind is not None and not isinstance(kind, str):
                return {"available": False, "reason": "invalid_response"}
            counts[kind if kind in ("web", "mobile") else "unknown"] += 1
        return {"available": True, "app_count": len(body), "app_types": counts}
    except Exception:  # noqa: BLE001 - upstream exception text may contain private app details
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Only fresh inventory stacks are eligible, never credential-map members."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_faro_apps(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "faro_apps: " + result["reason"])
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
