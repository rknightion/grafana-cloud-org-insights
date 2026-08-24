"""Small allow-listed inventories from each stack's own Grafana HTTP API."""

from __future__ import annotations

import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient

SEARCH_PATH = "api/search/"
DATASOURCES_PATH = "api/datasources"
SEARCH_PAGE_SIZE = 5000  # Grafana's documented maximum.
MAX_PAGES = 100
CONCURRENCY = 12

OK = "ok"
NO_CREDENTIAL = "no_credential"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
INVALID_RESPONSE = "invalid_response"
TRUNCATED = "truncated"
INVALID_URL = "invalid_url"
INCOMPLETE_INVENTORY = "incomplete_inventory"


def unavailable(slug: str, reason: str, detail: str = "") -> dict[str, Any]:
    return {"slug": slug, "available": False, "reason": reason, "detail": detail[:240]}


def _reason(status: int) -> str:
    return {401: UNAUTHORISED, 403: FORBIDDEN}.get(status, HTTP_ERROR)


def validated_base_url(stack: Mapping[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    slug = str(stack.get("slug") or "")
    raw = stack.get("url")
    if not isinstance(raw, str) or not raw.strip():
        return None, unavailable(slug, INVALID_URL, "inventory carries no valid url")
    try:
        parsed = urllib.parse.urlsplit(raw)
        _ = parsed.port
    except ValueError:
        return None, unavailable(slug, INVALID_URL, "inventory carries no valid url")
    if (
        raw != raw.strip()
        or any(char.isspace() for char in raw)
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or bool(parsed.query)
        or bool(parsed.fragment)
    ):
        return None, unavailable(slug, INVALID_URL, "inventory carries no valid url")
    return raw.rstrip("/"), None


def _body(response: Any, slug: str, what: str) -> tuple[Any | None, dict[str, Any] | None]:
    if not response.ok:
        return None, unavailable(slug, _reason(response.status), f"{what}: HTTP {response.status}")
    try:
        return response.json(), None
    except Exception as exc:  # noqa: BLE001 - malformed JSON is a source state
        return None, unavailable(slug, INVALID_RESPONSE,
                                 f"{what}: invalid JSON ({type(exc).__name__})")


def probe_dashboards_stack(
    client: ReadOnlyClient, stack: Mapping[str, Any], token: str,
) -> dict[str, Any]:
    """Enumerate the complete search result, never a top-N sample."""
    slug = str(stack.get("slug") or "")
    base, error = validated_base_url(stack)
    if error:
        return error
    if not token:
        return unavailable(slug, NO_CREDENTIAL, "no stored per-stack reader token")
    expected = stack.get("dashboardCnt")
    if isinstance(expected, bool) or not isinstance(expected, int) or expected < 0:
        return unavailable(
            slug, INVALID_RESPONSE,
            "inventory carries no valid dashboardCnt for completeness verification",
        )

    dashboards: list[dict[str, str]] = []
    seen: set[str] = set()
    for page in range(1, MAX_PAGES + 1):
        try:
            response = client.get(
                f"{base}/{SEARCH_PATH}",
                params={"type": "dash-db", "limit": SEARCH_PAGE_SIZE, "page": page},
                bearer=token,
            )
        except Exception as exc:  # noqa: BLE001 - one stack must not fail the estate
            return unavailable(slug, TRANSPORT_ERROR, f"dashboard search: {type(exc).__name__}")
        batch, error = _body(response, slug, "dashboard search")
        if error:
            return error
        if not isinstance(batch, list) or not all(isinstance(item, Mapping) for item in batch):
            return unavailable(slug, INVALID_RESPONSE,
                               "dashboard search is not an array of objects")
        for index, item in enumerate(batch):
            uid, title, kind = item.get("uid"), item.get("title"), item.get("type")
            if not isinstance(uid, str) or not uid:
                return unavailable(slug, INVALID_RESPONSE,
                                   f"dashboard search page {page} item {index} has invalid uid")
            if uid in seen:
                return unavailable(slug, INVALID_RESPONSE,
                                   f"dashboard uid {uid!r} was repeated")
            if not isinstance(title, str) or not title or kind != "dash-db":
                return unavailable(slug, INVALID_RESPONSE,
                                   f"dashboard search page {page} item {index} is malformed")
            folder = item.get("folderTitle")
            if folder is not None and not isinstance(folder, str):
                return unavailable(slug, INVALID_RESPONSE,
                                   f"dashboard search page {page} item {index} has invalid folder")
            seen.add(uid)
            dashboards.append({"uid": uid, "title": title, "folder": folder or ""})
        if len(batch) < SEARCH_PAGE_SIZE:
            if len(dashboards) != expected:
                return unavailable(
                    slug, INCOMPLETE_INVENTORY,
                    f"dashboard search returned {len(dashboards)} of inventory dashboardCnt={expected}",
                )
            return {
                "slug": slug, "available": True, "reason": OK,
                "completeness": "paged_to_short_response", "dashboards": dashboards,
            }
    return unavailable(slug, TRUNCATED,
                       f"dashboard search still returned full pages after {MAX_PAGES} pages")


def probe_datasources_stack(
    client: ReadOnlyClient, stack: Mapping[str, Any], token: str,
) -> dict[str, Any]:
    slug = str(stack.get("slug") or "")
    base, error = validated_base_url(stack)
    if error:
        return error
    if not token:
        return unavailable(slug, NO_CREDENTIAL, "no stored per-stack reader token")
    try:
        response = client.get(f"{base}/{DATASOURCES_PATH}", bearer=token)
    except Exception as exc:  # noqa: BLE001
        return unavailable(slug, TRANSPORT_ERROR, f"datasources: {type(exc).__name__}")
    body, error = _body(response, slug, "datasources")
    if error:
        return error
    if not isinstance(body, list) or not all(isinstance(item, Mapping) for item in body):
        return unavailable(slug, INVALID_RESPONSE, "datasources is not an array of objects")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(body):
        values = (item.get("uid"), item.get("name"), item.get("type"))
        if not all(isinstance(value, str) and value for value in values):
            return unavailable(slug, INVALID_RESPONSE,
                               f"datasource item {index} has invalid uid, name or type")
        uid, name, kind = values
        if uid in seen:
            return unavailable(slug, INVALID_RESPONSE, f"datasource uid {uid!r} was repeated")
        seen.add(uid)
        rows.append({"uid": uid, "name": name, "type": kind})
    return {"slug": slug, "available": True, "reason": OK, "datasources": rows}


def _probe_all(
    probe: Callable[[ReadOnlyClient, Mapping[str, Any], str], dict[str, Any]],
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    concurrency: int = CONCURRENCY,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    selected = [stack for stack in stacks
                if stack.get("slug") and stack.get("status") != "paused"]

    def one(stack: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        slug = str(stack.get("slug") or "")
        token = str((credentials.get(slug) or {}).get("token") or "")
        record = probe(client, stack, token)
        if not record.get("available") and on_error is not None:
            on_error(slug, f"{record.get('reason')}: {record.get('detail', '')}".strip())
        return slug, record

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(one, selected))


def probe_dashboards_all(
    client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]], **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    return _probe_all(probe_dashboards_stack, client, stacks, credentials, **kwargs)


def probe_datasources_all(
    client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]], **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    return _probe_all(probe_datasources_stack, client, stacks, credentials, **kwargs)
