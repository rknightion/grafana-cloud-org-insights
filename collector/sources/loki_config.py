"""Read effective Loki retention and the stack-local retention request queue.

The effective limits endpoint is a Loki dataplane read, so it uses the organisation CAP with the
stack's Loki tenant id as HTTP basic-auth user.  Retention requests live behind the Grafana plugin
resource endpoint and use the existing per-stack reader.  They are deliberately independent reads:
one unavailable route must not turn a readable route into an invented zero.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Mapping, Sequence

from collector.httpclient import ReadOnlyClient

LIMITS_PATH = "config/tenant/v1/limits"
RETENTION_REQUESTS_PATH = "api/plugins/grafana-dbcfg-app/resources/v1/lokiconfigretentions"
SETTINGS_PATH = "api/plugins/grafana-dbcfg-app/resources/v1/settings"

OK = "ok"
NO_CREDENTIAL = "no_credential"
NO_LOKI_INSTANCE = "no_loki_instance"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
NOT_FOUND = "endpoint_absent_404"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"
INVALID_RESPONSE = "invalid_response"


def unavailable(slug: str, state: str, detail: str = "") -> dict[str, Any]:
    """A domain-specific unavailable record, safe to join by inventory slug."""
    return {"available": False, "slug": slug, "state": state, "detail": detail[:240]}


def _state_for(status: int) -> str:
    return {401: UNAUTHORISED, 403: FORBIDDEN, 404: NOT_FOUND}.get(status, HTTP_ERROR)


def _limits_record(client: ReadOnlyClient, stack: Mapping[str, Any], cap: str) -> dict[str, Any]:
    slug = str(stack.get("slug") or "")
    base = stack.get("hlInstanceUrl")
    tenant = stack.get("hlInstanceId")
    if not isinstance(base, str) or not base.strip() or tenant is None or tenant == "":
        return unavailable(slug, NO_LOKI_INSTANCE, "inventory has no usable Loki endpoint or tenant id")
    if not cap:
        return unavailable(slug, NO_CREDENTIAL, "no organisation CAP")
    try:
        response = client.get(f"{base.rstrip('/')}/{LIMITS_PATH}", basic=(str(tenant), cap))
    except Exception as exc:  # noqa: BLE001 - one stack must not fail the estate sweep
        return unavailable(slug, TRANSPORT_ERROR, type(exc).__name__)
    if not response.ok:
        return unavailable(slug, _state_for(response.status), f"HTTP {response.status}")
    try:
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - malformed JSON is an explicit state
        return unavailable(slug, INVALID_RESPONSE, f"invalid JSON ({type(exc).__name__})")
    if not isinstance(body, Mapping):
        return unavailable(slug, INVALID_RESPONSE, f"expected object, got {type(body).__name__}")
    streams = body.get("retention_stream")
    if streams is not None and (
        not isinstance(streams, list) or not all(isinstance(item, Mapping) for item in streams)
    ):
        return unavailable(slug, INVALID_RESPONSE, "retention_stream is not a list of objects")
    record: dict[str, Any] = {"available": True, "slug": slug, "state": OK}
    # The key being absent is distinct from a successful empty stream list.  It means this API version
    # did not disclose the state needed for a policy comparison, so the pillar must withhold that check.
    if streams is not None:
        record["retention_stream"] = [dict(item) for item in streams]
    return record


def _request_item(item: Mapping[str, Any]) -> dict[str, Any]:
    spec = item.get("spec")
    status = item.get("status")
    spec = spec if isinstance(spec, Mapping) else {}
    status = status if isinstance(status, Mapping) else {}
    pr_info = status.get("pr_info")
    pr_info = pr_info if isinstance(pr_info, Mapping) else {}
    shared = {"author", "message", "request_timestamp"}
    # An unknown spec field is part of the API's user request and must survive untouched.  `limit` is
    # also surfaced in its own display column, but remains in opaque so no extension is discarded.
    opaque = {key: value for key, value in spec.items() if key not in shared}
    return {
        "author": spec.get("author"),
        "message": spec.get("message"),
        "request_timestamp": spec.get("request_timestamp"),
        "limit": opaque.get("limit"),
        "opaque": opaque,
        "status": status.get("status"),
        "processed_timestamp": status.get("processed_timestamp"),
        "pr_number": pr_info.get("number"),
    }


def _requests_record(client: ReadOnlyClient, stack: Mapping[str, Any], token: str) -> dict[str, Any]:
    slug = str(stack.get("slug") or "")
    base = stack.get("url")
    if not isinstance(base, str) or not base.strip():
        return unavailable(slug, INVALID_RESPONSE, "inventory has no usable stack URL")
    if not token:
        return unavailable(slug, NO_CREDENTIAL, "no stored per-stack reader token")
    try:
        response = client.get(f"{base.rstrip('/')}/{RETENTION_REQUESTS_PATH}", bearer=token)
    except Exception as exc:  # noqa: BLE001 - one stack must not fail the estate sweep
        return unavailable(slug, TRANSPORT_ERROR, type(exc).__name__)
    if not response.ok:
        return unavailable(slug, _state_for(response.status), f"HTTP {response.status}")
    try:
        body = response.json()
    except Exception as exc:  # noqa: BLE001 - malformed JSON is an explicit state
        return unavailable(slug, INVALID_RESPONSE, f"invalid JSON ({type(exc).__name__})")
    items = body.get("items") if isinstance(body, Mapping) else None
    if not isinstance(items, list) or not all(isinstance(item, Mapping) for item in items):
        return unavailable(slug, INVALID_RESPONSE, "expected items list of objects")
    return {"available": True, "slug": slug, "state": OK,
            "items": [_request_item(item) for item in items]}


def probe_stack(
    client: ReadOnlyClient,
    stack: Mapping[str, Any],
    cap: str,
    token: str,
) -> dict[str, Any]:
    """Read one stack's effective Loki limits and independent request queue using only GET."""
    return {
        "slug": str(stack.get("slug") or ""),
        "limits": _limits_record(client, stack, cap),
        "change_requests": _requests_record(client, stack, token),
    }


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    cap: str,
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    concurrency: int = 12,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, Any]:
    """Probe the live inventory only; credential-only departed stacks never enter the output."""
    results: dict[str, Any] = {}

    def one(stack: Mapping[str, Any]) -> None:
        slug = str(stack.get("slug") or "")
        if not slug or stack.get("status") == "paused":
            return
        token = str((credentials.get(slug) or {}).get("token") or "")
        try:
            results[slug] = probe_stack(client, stack, cap, token)
        except Exception as exc:  # noqa: BLE001 - defensive boundary around an individual stack
            results[slug] = {
                "slug": slug,
                "limits": unavailable(slug, TRANSPORT_ERROR, type(exc).__name__),
                "change_requests": unavailable(slug, TRANSPORT_ERROR, type(exc).__name__),
            }
            if on_error:
                on_error(slug, f"loki_config: {type(exc).__name__}")

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(one, stacks))
    return results
