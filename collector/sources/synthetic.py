"""Opt-in GET-only Synthetic Monitoring list projection. No product detail survives parse."""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from collector.httpclient import ReadOnlyClient
from collector.provision import synthetic_datasource_uid
from collector.sources.stack_catalog import validated_base_url

CHECK_TYPES = ("http", "ping", "dns", "tcp", "traceroute", "scripted", "multihttp",
               "grpc", "browser", "unknown")
MAX_ITEMS = 100_000


def _items(body):
    return (isinstance(body, list) and len(body) <= MAX_ITEMS
            and all(isinstance(item, Mapping) for item in body))


def probe_stack(client: ReadOnlyClient, stack: Mapping[str, Any], reader: str) -> dict[str, Any]:
    """Only fixed counts and closed failure enums escape, even on exceptions."""
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    if not reader:
        return {"available": False, "reason": "no_credential"}
    try:
        response = client.get(base + "/api/datasources", bearer=reader, guarded=True,
                              synthetic=True)
        if not response.ok:
            return {"available": False, "reason": "unreadable"}
        uid, state = synthetic_datasource_uid(response.json())
        if uid is None:
            return {"available": False, "reason": state}
        prefix = base + f"/api/datasources/proxy/uid/{uid}/sm/"
        checks = client.get(prefix + "check/list", bearer=reader, guarded=True, synthetic=True)
        if not checks.ok:
            return {"available": False, "reason": "checks_unreadable"}
        checks = checks.json()
        probes = client.get(prefix + "probe/list", bearer=reader, guarded=True, synthetic=True)
        if not probes.ok:
            return {"available": False, "reason": "probes_unreadable"}
        probes = probes.json()
        if not _items(checks) or not _items(probes):
            return {"available": False, "reason": "invalid_schema"}
        counts = dict.fromkeys(CHECK_TYPES, 0)
        enabled = 0
        for check in checks:
            if not isinstance(check.get("enabled"), bool) or not isinstance(check.get("settings"), Mapping):
                return {"available": False, "reason": "invalid_schema"}
            kinds = list(check["settings"])
            kind = kinds[0] if len(kinds) == 1 and kinds[0] in CHECK_TYPES else "unknown"
            counts[kind] += 1
            enabled += int(check["enabled"])
        probe_counts = {"public": 0, "private": 0}
        for probe in probes:
            if not isinstance(probe.get("public"), bool):
                return {"available": False, "reason": "invalid_schema"}
            probe_counts["public" if probe["public"] else "private"] += 1
        return {"available": True, "check_count": len(checks), "enabled_count": enabled,
                "check_type_counts": counts, "probe_counts": probe_counts}
    except Exception:  # noqa: BLE001 - never emit raw targets, response bodies or exception text
        return {"available": False, "reason": "transport_error"}


def probe_all(client: ReadOnlyClient, stacks: Sequence[Mapping[str, Any]],
              credentials: Mapping[str, Mapping[str, Any]], *, concurrency: int = 8,
              on_error: Callable[[str, str], None] | None = None) -> dict[str, Any]:
    def probe(stack):
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        record = probe_stack(client, stack, token)
        if not record["available"] and on_error:
            on_error(slug, f"synthetic_inventory: {record['reason']}")
        return slug, record
    live = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        return dict(pool.map(probe, live))
