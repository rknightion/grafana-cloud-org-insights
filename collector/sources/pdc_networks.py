"""Count attributed PDC policies only after complete fresh-region coverage.

The credential also permits a tokens GET. This collector never calls that route.
Only scalar counts and closed reasons leave this module; IDs are transient.
"""
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
import re
from typing import Any, Callable
from urllib.parse import parse_qsl, urljoin, urlsplit

from collector.config import GCOM
from collector.httpclient import ReadOnlyClient
from collector.sources import gcom
from collector.sources.resource_schema import UnsafeSchema, guard_resource
from collector.sources.stack_catalog import validated_base_url

PATH = "/api/plugin-proxy/grafana-pdc-app/grafanacom-api/v1/accesspolicies"
MAX_PAGES = 100
MAX_POLICIES = 100_000
DECIMAL = re.compile(r"[1-9][0-9]{0,19}")
REGION = re.compile(r"[a-z0-9][a-z0-9-]{0,99}")


def unavailable(reason):
    return {"available": False, "reason": reason}


def next_cursor(link, filters):
    """Validate the gcom continuation contract; never request its supplied URL.

    gcom.fetch_access_policies resolves links under GCOM. Admit that same origin
    and accesspolicies path, but only a cursor and unchanged explicit filters.
    The stack proxy request is always reconstructed separately.
    """
    if (not isinstance(link, str) or not link or len(link) > 4096
            or "\\" in link or any(ord(c) <= 32 or ord(c) > 126 for c in link)):
        raise ValueError("invalid_continuation")
    expected = urlsplit(GCOM)
    parsed = urlsplit(urljoin(GCOM + "/", link.lstrip("/")))
    pairs = parse_qsl(parsed.query, keep_blank_values=True, strict_parsing=True)
    query = dict(pairs)
    if (parsed.scheme != expected.scheme or parsed.netloc != expected.netloc
            or parsed.path != expected.path + "/v1/accesspolicies"
            or parsed.fragment or "%" in parsed.path
            or len(pairs) != len(query)
            or set(query) - {"pageCursor", *filters}
            or any(query[key] != value for key, value in filters.items() if key in query)):
        raise ValueError("invalid_continuation")
    cursor = query.get("pageCursor")
    if not cursor or len(cursor) > 2048 or any(ord(char) < 33 or ord(char) > 126 for char in cursor):
        raise ValueError("invalid_continuation")
    return cursor


def fetch_pdc_networks(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str,
                       regions: Sequence[str]) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return unavailable("invalid_url")
    stack_id = stack.get("id")
    if (isinstance(stack_id, bool) or not isinstance(stack_id, (int, str))
            or not DECIMAL.fullmatch(str(stack_id))):
        return unavailable("invalid_stack_id")
    if not regions or any(not isinstance(r, str) or not REGION.fullmatch(r) for r in regions):
        return unavailable("invalid_regions")
    if not reader:
        return unavailable("no_credential")
    identities: dict[str, bool] = {}
    objects = 0
    try:
        for region in regions:
            filters = {"region": region, "realmType": "stack", "realmIdentifier": str(stack_id)}
            params = dict(filters)
            cursors = set()
            for _ in range(MAX_PAGES):
                response = client.get(base + PATH, params=params, bearer=reader, guarded=True)
                if response.status != 200:
                    return unavailable("unreadable")
                body = response.json()
                if (not isinstance(body, dict) or set(body) != {"items", "metadata"}
                        or not isinstance(body["items"], list)
                        or not isinstance(body["metadata"], dict)
                        or set(body["metadata"]) != {"pagination"}
                        or not isinstance(body["metadata"]["pagination"], dict)
                        or set(body["metadata"]["pagination"]) != {"nextPage"}):
                    return unavailable("invalid_response")
                objects += len(body["items"])
                if objects > MAX_POLICIES:
                    return unavailable("limit_exceeded")
                guard_resource(body)
                for policy in body["items"]:
                    if not isinstance(policy, dict):
                        return unavailable("invalid_response")
                    policy_id, realms, scopes = policy.get("id"), policy.get("realms"), policy.get("scopes")
                    if (not isinstance(policy_id, str) or not policy_id.strip() or len(policy_id) > 256
                            or not isinstance(realms, list) or not realms
                            or not isinstance(scopes, list)
                            or any(not isinstance(s, str) or not s.strip() for s in scopes)):
                        return unavailable("invalid_response")
                    for realm in realms:
                        if (not isinstance(realm, dict) or realm.get("type") not in {"stack", "org"}
                                or not isinstance(realm.get("identifier"), (str, int))
                                or isinstance(realm.get("identifier"), bool)
                                or not DECIMAL.fullmatch(str(realm["identifier"]))):
                            return unavailable("invalid_response")
                    matches = "set:pdc-signing" in scopes and any(
                        r["type"] == "stack" and str(r["identifier"]) == str(stack_id) for r in realms)
                    if policy_id in identities and identities[policy_id] != matches:
                        return unavailable("invalid_response")
                    identities[policy_id] = matches
                link = body["metadata"]["pagination"]["nextPage"]
                if link is None:
                    break
                cursor = next_cursor(link, filters)
                if cursor in cursors:
                    return unavailable("invalid_continuation")
                cursors.add(cursor)
                params = {**filters, "pageCursor": cursor}
            else:
                return unavailable("limit_exceeded")
        return {"available": True, "network_count": sum(identities.values())}
    except UnsafeSchema:
        return unavailable("unsafe_schema")
    except ValueError:
        return unavailable("invalid_response")
    except Exception:  # noqa: BLE001 - private upstream content must never enter errors
        return unavailable("transport_error")


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None,
              inventory: Sequence[Mapping[str, Any]] | None = None) -> dict[str, Any]:
    """Regions use full fresh inventory; limited scans probe only selected stacks."""
    estate = stacks if inventory is None else inventory
    regions = gcom.policy_regions(estate)
    # Missing region data means unknown estate coverage, not a control-realms-only count.
    complete_regions = bool(estate) and all(isinstance(s.get("regionSlug"), str)
                                           and REGION.fullmatch(s["regionSlug"]) for s in estate)
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        result = (fetch_pdc_networks(client, stack, token, regions) if complete_regions
                  else unavailable("invalid_regions"))
        if not result["available"] and on_error:
            on_error(slug, "pdc_networks: " + result["reason"])
        return slug, result
    selected = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, selected))
