"""Public dashboards, ENUMERATED per stack rather than inferred from view events.

Read through each stack's own API with the per-stack reader token; the role grant is
`dashboards.public:read`, and without it the endpoint is one of the four in this product that answer
**200 with a permission-filtered list rather than 403**. A count taken without the action reads
`totalCount: 0`. That can look policy-compliant in a zero-tolerance deployment, which is why coverage
is reported beside the count.

## Why this exists when Pillar J already counts them

Pillar J derives public dashboards from usage-insights EVENTS, so it sees only the ones somebody has
opened. The two answer different questions and **a disagreement between them is itself the finding**:

- enumeration says a public dashboard EXISTS (the inventory and policy question)
- events say a public dashboard is being USED (the exposure question)

## `accessToken` is NEVER stored

It is the live public URL. Putting it in an S3 view would make the customer's exposed dashboard
reachable from our own artifacts, and our views are read by an Infinity datasource with a wide reader.
Dropped at the one seam every record passes through, with a test asserting it.
"""

from __future__ import annotations

from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient

PATH = "api/dashboards/public-dashboards"

NO_CREDENTIAL = "no_credential"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
TRUNCATED = "truncated"
OK = "ok"

#: Only `ok` means an empty list really is zero. Every other state means NOT MEASURED, and on a
#: policy check the difference is the whole point.
READABLE = frozenset({OK})

#: The live public URL. Never stored, never logged, never sampled.
DROPPED_FIELDS = ("accessToken",)

#: Per stack. Keep the named detail bounded; the complete count remains in the scalar result.
MAX_DETAIL = 25
PER_PAGE = 1000
MAX_PAGES = 100


def strip(record: Mapping[str, Any]) -> dict[str, Any]:
    """One public dashboard, without the token that makes it reachable."""
    return {k: v for k, v in record.items() if k not in DROPPED_FIELDS}


def record(item: Mapping[str, Any]) -> dict[str, Any]:
    """The fields worth keeping. `dashboardUid` identifies which dashboard to go and un-share."""
    return {
        "title": item.get("title"),
        "dashboard_uid": item.get("dashboardUid"),
        "enabled": bool(item.get("isEnabled")),
    }


def unavailable(slug: str, reason: str, detail: str = "") -> dict[str, Any]:
    return {"available": False, "slug": slug, "state": reason, "detail": detail}


def _reason_for(status: int) -> str:
    return {401: UNAUTHORISED, 403: FORBIDDEN}.get(status, HTTP_ERROR)


def probe_stack(client: ReadOnlyClient, stack: Mapping[str, Any], token: str) -> dict[str, Any]:
    """Enumerate every page for one stack and refuse to call a partial response successful.

    On an `ok` result, `total` is the API's count and `listed` is the validated number collected across
    all pages, so they are necessarily equal. The detail sample is bounded independently.
    """
    slug = str(stack.get("slug") or "")
    if not token:
        return unavailable(slug, NO_CREDENTIAL, "no stored token")
    url = str(stack.get("url") or f"https://{slug}.grafana.net").rstrip("/")
    items: list[dict[str, Any]] = []
    seen_uids: set[str] = set()
    total = 0
    for page in range(1, MAX_PAGES + 1):
        resp = client.get(f"{url}/{PATH}", params={"page": page, "perpage": PER_PAGE}, bearer=token)
        if not resp.ok:
            return unavailable(slug, _reason_for(resp.status), f"HTTP {resp.status}")
        body = resp.json()
        if not isinstance(body, dict):
            return unavailable(slug, HTTP_ERROR, f"expected an object, got {type(body).__name__}")
        raw_batch = body.get("publicDashboards")
        if not isinstance(raw_batch, list) or not all(isinstance(i, Mapping) for i in raw_batch):
            return unavailable(slug, HTTP_ERROR, "publicDashboards is not a list of objects")
        if body.get("page") != page:
            return unavailable(slug, TRUNCATED,
                               f"requested page {page} but response reported {body.get('page')!r}")
        batch = [strip(i) for i in raw_batch]
        raw_total = body.get("totalCount")
        if not isinstance(raw_total, int) or isinstance(raw_total, bool) or raw_total < 0:
            return unavailable(slug, HTTP_ERROR, f"invalid totalCount {raw_total!r}")
        page_total = raw_total
        if page == 1:
            total = page_total
        elif page_total != total:
            return unavailable(slug, TRUNCATED,
                               f"totalCount changed from {total} to {page_total} on page {page}")
        for item in batch:
            public_uid = str(item.get("uid") or "")
            if not public_uid:
                return unavailable(slug, HTTP_ERROR, "public dashboard is missing uid")
            if public_uid in seen_uids:
                return unavailable(slug, TRUNCATED,
                                   f"public dashboard uid {public_uid!r} was repeated")
            seen_uids.add(public_uid)
        items.extend(batch)
        if len(items) >= total or not batch:
            break
    if len(items) != total:
        return unavailable(slug, TRUNCATED,
                           f"listed {len(items)} public dashboards but API reported {total}")
    rows = [record(i) for i in items][:MAX_DETAIL]
    return {
        "available": True,
        "slug": slug,
        "state": OK,
        "total": total,
        "listed": len(items),
        "enabled": sum(1 for i in items if bool(i.get("isEnabled"))),
        "dashboards": rows,
    }


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Iterate the LIVE INVENTORY, look each credential up (CLAUDE.md golden rule)."""
    out: dict[str, Any] = {}
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug:
            continue
        if stack.get("status") == "paused":
            continue
        token = str((credentials.get(slug) or {}).get("token") or "")
        if not token:
            out[slug] = unavailable(slug, NO_CREDENTIAL,
                                    "no stored token - the daily provisioner has not reached it yet")
            continue
        try:
            out[slug] = probe_stack(client, stack, token)
        except Exception as exc:  # noqa: BLE001 - one stack must never fail the sweep
            out[slug] = unavailable(slug, TRANSPORT_ERROR, f"{type(exc).__name__}: {exc}")
            if on_error:
                on_error(slug, f"public_dashboards: {type(exc).__name__}")
    return out
