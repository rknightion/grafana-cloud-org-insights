"""Count only the approved AWS accounts GET; backend write isolation is unknown."""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any, Callable

from collector.httpclient import ReadOnlyClient
from collector.sources.resource_schema import UnsafeSchema, guard_resource
from collector.sources.stack_catalog import validated_base_url

MAX_ACCOUNTS = 100_000


def fetch_cloud_accounts(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    stack_id = stack.get("id")
    if (isinstance(stack_id, bool) or not isinstance(stack_id, (int, str))
            or not re.fullmatch(r"[1-9][0-9]{0,19}", str(stack_id))):
        return {"available": False, "reason": "invalid_stack_id"}
    if not reader:
        return {"available": False, "reason": "no_credential"}
    path = f"/api/plugin-proxy/grafana-csp-app/he-api/api/v2/stacks/{stack_id}/aws/accounts"
    try:
        response = client.get(base + path, bearer=reader, guarded=True)
        if response.status != 200:
            return {"available": False, "reason": "unreadable"}
        body = response.json()
        # Only the witnessed data-only array is supported; no paging or partial fields.
        if (not isinstance(body, dict) or set(body) != {"data"}
                or not isinstance(body["data"], list) or len(body["data"]) > MAX_ACCOUNTS):
            return {"available": False, "reason": "invalid_response"}
        guard_resource(body)
        if any(not isinstance(account, dict) or not isinstance(account.get("id"), str)
               or not account["id"].strip() for account in body["data"]):
            return {"available": False, "reason": "invalid_response"}
        return {"available": True, "account_count": len(body["data"])}
    except UnsafeSchema:
        return {"available": False, "reason": "unsafe_schema"}
    except Exception:  # noqa: BLE001 - upstream exceptions may contain private account content
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    """Left-join credentials onto fresh inventory, never account or credential populations."""
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = fetch_cloud_accounts(client, stack, token)
        if not result["available"] and on_error:
            on_error(slug, "cloud_accounts: " + result["reason"])
        return slug, result

    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
