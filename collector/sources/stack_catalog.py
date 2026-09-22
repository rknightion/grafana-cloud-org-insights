"""Small allow-listed inventories from each stack's own Grafana HTTP API."""

from __future__ import annotations

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
_PROMQL_ESCAPES = {
    "a": "\a", "b": "\b", "f": "\f", "n": "\n", "r": "\r", "t": "\t",
    "v": "\v", "\\": "\\",
}


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


def _promql_string(query: str, start: int) -> tuple[str | None, int] | None:
    """Decode one PromQL string literal using its documented Go-style escapes."""
    quote = query[start]
    end = start + 1
    value: list[str] = []
    valid = True
    while end < len(query):
        char = query[end]
        if char == quote:
            return ("".join(value) if valid else None), end + 1
        if quote == "`":
            value.append(char)
            end += 1
            continue
        if char in "\r\n":
            valid = False
            value.append(char)
            end += 1
            continue
        if char != "\\":
            value.append(char)
            end += 1
            continue
        end += 1
        if end >= len(query):
            return None
        escape = query[end]
        if escape == quote:
            value.append(quote)
            end += 1
            continue
        if escape in _PROMQL_ESCAPES:
            value.append(_PROMQL_ESCAPES[escape])
            end += 1
            continue
        if escape in "01234567":
            digits = query[end:end + 3]
            if len(digits) != 3 or any(digit not in "01234567" for digit in digits):
                valid = False
                end += 1
                continue
            codepoint = int(digits, 8)
            if codepoint > 0xFF:
                valid = False
            else:
                value.append(chr(codepoint))
            end += 3
            continue
        widths = {"x": 2, "u": 4, "U": 8}
        width = widths.get(escape)
        if width is None:
            valid = False
            end += 1
            continue
        digits = query[end + 1:end + 1 + width]
        if len(digits) != width or any(digit not in "0123456789abcdefABCDEF" for digit in digits):
            valid = False
            end += 1
            continue
        codepoint = int(digits, 16)
        if codepoint > 0x10FFFF or 0xD800 <= codepoint <= 0xDFFF:
            valid = False
        else:
            value.append(chr(codepoint))
        end += width + 1
    return None


def _promql_tokens(query: str) -> list[tuple[str, str]] | None:
    """Lex only the PromQL tokens needed to identify literal equality matchers."""
    tokens: list[tuple[str, str]] = []
    index = 0
    while index < len(query):
        char = query[index]
        if char.isspace():
            index += 1
            continue
        if char == "#":
            newline = query.find("\n", index + 1)
            index = len(query) if newline < 0 else newline + 1
            continue
        if char in "'\"`":
            decoded = _promql_string(query, index)
            if decoded is None:
                return None
            value, index = decoded
            tokens.append(("string" if value is not None else "invalid_string", value or ""))
            continue
        if char.isalpha() or char == "_":
            end = index + 1
            while end < len(query) and (query[end].isalnum() or query[end] == "_"):
                end += 1
            tokens.append(("identifier", query[index:end]))
            index = end
            continue
        if char == "{":
            tokens.append(("open", char))
            index += 1
            continue
        if char == "}":
            tokens.append(("close", char))
            index += 1
            continue
        if char == "=" and query[index:index + 2] not in ("==", "=~"):
            tokens.append(("equal", char))
            index += 1
            continue
        if query[index:index + 2] in ("==", "=~", "!=", "!~"):
            tokens.append(("other", query[index:index + 2]))
            index += 2
            continue
        tokens.append(("other", char))
        index += 1
    return tokens


def _closing_brace(tokens: Sequence[tuple[str, str]], start: int) -> int | None:
    depth = 1
    for index in range(start + 1, len(tokens)):
        if tokens[index][0] == "open":
            depth += 1
        elif tokens[index][0] == "close":
            depth -= 1
            if depth == 0:
                return index
    return None


def _matcher_identity_selectors(tokens: Sequence[tuple[str, str]]) -> set[str] | None:
    """Validate one complete matcher list and return its literal identity values."""
    values: set[str] = set()
    index = 0
    while index < len(tokens):
        if tokens[index] == ("other", "$"):
            if index + 1 >= len(tokens):
                return None
            if tokens[index + 1][0] == "identifier":
                index += 2
            elif tokens[index + 1][0] == "open":
                end = _closing_brace(tokens, index + 1)
                if end is None:
                    return None
                index = end + 1
            else:
                return None
        else:
            if index + 2 >= len(tokens):
                return None
            label_kind, label = tokens[index]
            operator = tokens[index + 1]
            value_kind, value = tokens[index + 2]
            if (
                label_kind not in ("identifier", "string")
                or operator not in (("equal", "="), ("other", "!="),
                                    ("other", "=~"), ("other", "!~"))
                or value_kind != "string"
            ):
                return None
            if label in DASHBOARD_IDENTITY_LABELS and operator == ("equal", "="):
                selector = value.strip()
                if selector:
                    values.add(selector)
            index += 3
        if index == len(tokens):
            break
        if tokens[index] != ("other", ","):
            return None
        index += 1
    return values


def _query_identity_selectors(query: str) -> set[str] | None:
    tokens = _promql_tokens(query)
    if tokens is None:
        return None
    values: set[str] = set()
    index = 0
    while index < len(tokens):
        kind, _value = tokens[index]
        if kind == "close":
            return None
        if kind != "open":
            index += 1
            continue
        end = _closing_brace(tokens, index)
        if end is None:
            return None
        if index > 0 and tokens[index - 1] == ("other", "$"):
            index = end + 1
            continue
        matcher_tokens = tokens[index + 1:end]
        selectors = _matcher_identity_selectors(matcher_tokens)
        if selectors is None:
            if any(
                token_kind in ("identifier", "string")
                and token_value in DASHBOARD_IDENTITY_LABELS
                for token_kind, token_value in matcher_tokens
            ):
                return None
            index = end + 1
            continue
        values.update(selectors)
        index = end + 1
    return values


def _identity_selectors(body: Any) -> list[str] | None:
    if not isinstance(body, Mapping) or not isinstance(body.get("dashboard"), Mapping):
        return None
    queries = _panel_queries(body["dashboard"])
    if queries is None:
        return None
    values: set[str] = set()
    for query in queries:
        selectors = _query_identity_selectors(query)
        if selectors is None:
            return None
        values.update(selectors)
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
