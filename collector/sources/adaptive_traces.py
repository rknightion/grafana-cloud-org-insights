"""Count-only Adaptive Traces inventory through the verified stack-local GET proxy.

The existing reader's complete role is operationally sufficient; this is not an isolated
minimal-permission claim. No role or credential changes belong here. Health404 is an unsupported
health route, not evidence that the working resource routes are absent. Config availability does
not establish enablement: the captured config has tunables, not an enabled flag. Achieved savings
remain on the usage datasource panels; recommendation actions/seeds cannot measure them.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Mapping, Sequence

from collector.httpclient import ReadOnlyClient
from collector.sources.stack_catalog import validated_base_url

PLUGIN = "grafana-adaptivetraces-app"
PATH = f"api/plugin-proxy/{PLUGIN}"
POLICY_TYPES = ("status_code", "latency", "volumetric", "diversity", "other")


def _read(client: ReadOnlyClient, base: str, resource: str, token: str) -> tuple[Any, str]:
    """Never return or log exception text or error response bodies."""
    try:
        response = client.get(f"{base}/{PATH}/{resource}", bearer=token)
        if not response.ok:
            return None, {401: "token_401", 403: "forbidden_403", 404: "not_found_404"}.get(
                response.status, "http_error")
        return response.json(), "ok"
    except Exception:  # noqa: BLE001 - isolate each resource without leaking payloads
        return None, "transport_error"


def probe_stack(client: ReadOnlyClient, stack: Mapping[str, Any], token: str) -> dict[str, Any]:
    base, error = validated_base_url(stack)
    if error:
        return {"available": False, "reason": "invalid_url"}
    # Probe first, but do not make an unsupported or broken health route gate supported resources.
    _, health = _read(client, base, "health", token)
    result: dict[str, Any] = {"available": False, "health_state": health}
    config, state = _read(client, base, "config", token)
    if state == "ok" and not isinstance(config, dict):
        state = "invalid_response"
    result["config_state"] = state
    result["config_available"] = True if state == "ok" else None
    # Config tunables, policy bodies and recommendation prose never leave this function.
    for resource in ("policies", "recommendations"):
        body, state = _read(client, base, resource, token)
        if state == "ok" and (not isinstance(body, list)
                              or any(not isinstance(row, dict) for row in body)):
            state = "invalid_response"
        if state == "ok" and resource == "recommendations" and any(
            any(not isinstance(row.get(flag), bool) for flag in ("applied", "dismissed", "stale"))
            for row in body
        ):
            state = "invalid_response"
        result[f"{resource}_state"] = state
        if state != "ok":
            continue
        if resource == "policies":
            counts = dict.fromkeys(POLICY_TYPES, 0)
            for row in body:
                kind = row.get("type")
                counts[kind if isinstance(kind, str) and kind in counts else "other"] += 1
            result.update(policy_count=len(body), policy_type_counts=counts)
        else:
            result.update(
                recommendation_count=len(body),
                pending_recommendation_count=sum(
                    not any(row[flag] for flag in ("applied", "dismissed", "stale"))
                    for row in body
                ),
            )
    result["available"] = any(result[f"{key}_state"] == "ok"
                              for key in ("config", "policies", "recommendations"))
    return result


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    """Discover from the live inventory; credentials are only a left-join lookup."""
    def one(stack: Mapping[str, Any]) -> tuple[str, dict[str, Any]]:
        slug = str(stack["slug"])
        token = str((credentials.get(slug) or {}).get("token") or "")
        if not token:
            return slug, {"available": False, "reason": "no_credential"}
        return slug, probe_stack(client, stack, token)

    active = [s for s in stacks if s.get("slug") and s.get("status") != "paused"]
    with ThreadPoolExecutor(max_workers=12) as pool:
        return dict(pool.map(one, active))
