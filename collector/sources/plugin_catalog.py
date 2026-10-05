"""Anonymous current public plugin metadata, never installed-version entitlement.

Call only at the process edge, with the fresh inventory. This source does no estate
fetching, credential lookup or publication. Signature/publisher identity is not an
Enterprise classifier: both Aurora and Infinity have Grafana signatures.

Contract witnesses at Grafana revision 6e5fb9d9729c94b2a0f51b66ee92949684af9824:
public/app/features/plugins/admin/types.ts declares RemotePlugin status/typeCode;
public/app/features/plugins/admin/helpers.ts maps status=enterprise to isEnterprise;
public/app/features/plugins/admin/components/PluginListItemBadges.tsx displays it.
The minimized real responses and their observation/digests live in plugin_catalog
fixtures. Catalogue version is current metadata, not what any stack has installed.
"""
from collections.abc import Mapping, Sequence
import re
from typing import Any

from collector.httpclient import ReadOnlyClient

BASE_URL = "https://grafana.com/api/plugins/"
# Local route-safety and resource bounds, not a maintained catalogue or plugin set.
MAX_PLUGINS = 1000
PLUGIN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[A-Za-z0-9.-]+)?(?:\+[A-Za-z0-9.-]+)?")


def _unavailable(reason: str) -> dict[str, Any]:
    return {"available": False, "reason": reason}


def _fetch(client: ReadOnlyClient, slug: str) -> dict[str, Any]:
    try:
        # No bearer, basic auth or customer headers. Guarded GET fences queue/DNS/
        # complete-read caller waits and refuses redirects; no supplied URLs followed.
        response = client.get(BASE_URL + slug, guarded=True)
        if response.status != 200:
            return _unavailable("unreadable")
        try:
            body = response.json()
        except (ValueError, UnicodeError):
            return _unavailable("invalid_response")
        if not isinstance(body, dict):
            return _unavailable("invalid_response")
        if body.get("slug") != slug or body.get("typeCode") != "datasource":
            return _unavailable("metadata_mismatch")
        status = body.get("status")
        # Pending, deprecated, deleted, absent and future statuses are unknown,
        # not negative classifications. Neither signing nor author is consulted.
        if status != "enterprise" and status != "active":
            return _unavailable("unknown_status")
        result: dict[str, Any] = {
            "available": True, "enterprise": status == "enterprise", "status": status,
            "basis": "current_public_catalogue",
        }
        version = body.get("version")
        if isinstance(version, str) and len(version) <= 128 and VERSION.fullmatch(version):
            result["version"] = version
        return result
    except Exception:  # noqa: BLE001 - never retain raw errors, URLs or author metadata
        return _unavailable("transport_error")


def fetch_catalogue(client: ReadOnlyClient,
                    freshstacks: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Discover safe IDs from fresh inventory keys; one anonymous bounded GET per ID.

    Repeated types are deduplicated. Zero configured counts still have metadata;
    malformed IDs are excluded without requests. If discovery exceeds the read
    budget, mark every discovered safe ID unavailable rather than choosing a subset.
    Each read uses the client's timeout/deadline; callers should configure a run
    deadline as for other process-edge sources. No caching or carried estate state.
    """
    ids: set[str] = set()
    for stack in freshstacks:
        counts = stack.get("datasourceCnts")
        if isinstance(counts, Mapping):
            ids.update(slug for slug in counts
                       if isinstance(slug, str) and PLUGIN_ID.fullmatch(slug))
    if len(ids) > MAX_PLUGINS:
        return {slug: _unavailable("discovery_limit") for slug in sorted(ids)}
    return {slug: _fetch(client, slug) for slug in sorted(ids)}
