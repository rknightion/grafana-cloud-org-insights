"""Small allow-listed inventories from each stack's own Grafana HTTP API."""

from __future__ import annotations

import json
import re
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient

SEARCH_PATH = "api/search/"
DASHBOARD_DETAIL_PATH = "api/dashboards/uid"
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

# Canonical Pillar K identities come from service_name. `job` was measured live and resolved none of
# 35 values, so widening this list would manufacture a bridge between disjoint namespaces.
DASHBOARD_IDENTITY_LABELS = ("service_name",)
_LITERAL_IDENTITY_SELECTOR = re.compile(
    r'(?<![A-Za-z0-9_])(' + "|".join(map(re.escape, DASHBOARD_IDENTITY_LABELS))
    + r')\s*=\s*"((?:\\.|[^"\\])*)"'
)


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


def _panel_queries(dashboard: Mapping[str, Any]) -> list[str] | None:
    panels = dashboard.get("panels", [])
    if not isinstance(panels, list) or not all(isinstance(panel, Mapping) for panel in panels):
        return None
    queries: list[str] = []

    def visit(panel: Mapping[str, Any]) -> bool:
        targets = panel.get("targets", [])
        if not isinstance(targets, list) or not all(isinstance(target, Mapping) for target in targets):
            return False
        for target in targets:
            # These are the query-bearing fields used by Grafana's Prometheus and Loki datasources.
            # The raw strings are inspected in memory and never retained in the source payload.
            for key in ("expr", "query"):
                value = target.get(key)
                if isinstance(value, str):
                    queries.append(value)
        children = panel.get("panels", [])
        if not isinstance(children, list) or not all(isinstance(child, Mapping) for child in children):
            return False
        return all(visit(child) for child in children)

    return queries if all(visit(panel) for panel in panels) else None


def _identity_selectors(body: Any) -> list[str] | None:
    if not isinstance(body, Mapping) or not isinstance(body.get("dashboard"), Mapping):
        return None
    queries = _panel_queries(body["dashboard"])
    if queries is None:
        return None
    values: set[str] = set()
    for query in queries:
        for _label, encoded in _LITERAL_IDENTITY_SELECTOR.findall(query):
            try:
                value = json.loads(f'"{encoded}"')
            except json.JSONDecodeError:
                return None
            if isinstance(value, str) and value.strip():
                values.add(value.strip())
    return sorted(values, key=str.casefold)


def _attach_dashboard_details(
    client: ReadOnlyClient, slug: str, base: str, token: str,
    dashboards: list[dict[str, Any]],
) -> dict[str, Any]:
    detailed: list[dict[str, Any]] = []
    for dashboard in dashboards:
        uid = str(dashboard["uid"])
        try:
            response = client.get(
                f"{base}/{DASHBOARD_DETAIL_PATH}/{urllib.parse.quote(uid, safe='')}", bearer=token,
            )
        except Exception as exc:  # noqa: BLE001 - one failed detail invalidates the stack census
            return {
                "detail_available": False, "detail_reason": TRANSPORT_ERROR,
                "detail": f"dashboard detail: {type(exc).__name__}"[:240],
            }
        body, error = _body(response, slug, "dashboard detail")
        if error:
            return {
                "detail_available": False, "detail_reason": error["reason"],
                "detail": error.get("detail", ""),
            }
        selectors = _identity_selectors(body)
        if selectors is None:
            return {
                "detail_available": False, "detail_reason": INVALID_RESPONSE,
                "detail": "dashboard detail has invalid dashboard or panel query structure",
            }
        detailed.append({**dashboard, "identity_selectors": selectors})
    return {"detail_available": True, "detail_reason": "", "dashboards": detailed}


def probe_dashboards_stack(
    client: ReadOnlyClient, stack: Mapping[str, Any], token: str,
    *, include_detail: bool = False,
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

    dashboards: list[dict[str, Any]] = []
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
            tags = item.get("tags", [])
            if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
                return unavailable(slug, INVALID_RESPONSE,
                                   f"dashboard search page {page} item {index} has invalid tags")
            seen.add(uid)
            # Tags are tenant-authored and can contain arbitrary identity detail. Pillar K needs only
            # the explicit service contract, so unrelated tags are discarded at the source boundary.
            service_tags = [tag for tag in tags if tag.casefold().startswith("service:")]
            dashboards.append({
                "uid": uid, "title": title, "folder": folder or "",
                "service_tags": service_tags,
            })
        if len(batch) < SEARCH_PAGE_SIZE:
            if len(dashboards) != expected:
                return unavailable(
                    slug, INCOMPLETE_INVENTORY,
                    f"dashboard search returned {len(dashboards)} of inventory dashboardCnt={expected}",
                )
            result = {
                "slug": slug, "available": True, "reason": OK,
                "completeness": "paged_to_short_response", "dashboards": dashboards,
                "detail_enabled": include_detail,
            }
            if include_detail:
                detail = _attach_dashboard_details(client, slug, base, token, dashboards)
                if detail.get("detail_available"):
                    result.update(detail)
                else:
                    result.update(detail)
                    # Never expose partial selector evidence: it would score early dashboards while
                    # treating later failed reads as a trustworthy no.
                    result["dashboards"] = dashboards
            return result
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
        if on_error is not None:
            if not record.get("available"):
                on_error(slug, f"{record.get('reason')}: {record.get('detail', '')}".strip())
            elif record.get("detail_available") is False:
                on_error(
                    slug,
                    f"{record.get('detail_reason')}: {record.get('detail', '')}".strip(),
                )
        return slug, record

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(one, selected))


def probe_dashboards_all(
    client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]], **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    include_detail = bool(kwargs.pop("include_detail", False))
    return _probe_all(
        lambda source_client, stack, token: probe_dashboards_stack(
            source_client, stack, token, include_detail=include_detail,
        ),
        client, stacks, credentials, **kwargs,
    )


def probe_datasources_all(
    client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]], **kwargs: Any,
) -> dict[str, dict[str, Any]]:
    return _probe_all(probe_datasources_stack, client, stacks, credentials, **kwargs)
