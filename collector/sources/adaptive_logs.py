"""Adaptive Logs recommendations, read through each stack's own app-plugin proxy.

Auth is the persistent per-stack reader token from `collector/credentials.py` - the same credential the
Assistant and usage-insights sweeps use. The role grant is `plugins.app:access` on
`plugins:id:grafana-adaptivelogs-app` plus `grafana-adaptivelogs-app.patterns:read`, which is exactly
Grafana's documented **Patterns Reader** role.

## Three findings that decide how this data may be presented

**1. `volume` is the RESIDUAL volume still flowing, not the pre-drop volume.** A pattern already being
dropped can report almost no residual volume. So the PENDING saving is computable and the
**ALREADY-APPLIED saving is not** -
there is no field from which the pre-drop volume can be recovered.

The applied half is not lost, it is just somewhere else: `grafanacloud-usage` carries
`grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second`, a real rate, on every stack with no
credential at all. Pillar B reads that directly. This module owns the pending half only.

**2. The window is UNSTATED and cannot be set.** `/recommendations` is the only route the proxy exposes
(`/config`, `/settings`, `/policies`, `/status`, `/recommendations/summary` all 404) and it ignores
`?window=`, `?from=`/`?to=`, `?range=` and `?days=` - all four return a byte-identical payload. So
`volume` is a total over a period the API does not name, and **it must never be divided into a rate.**
Cross-checking it against an independently measured daily rate can disprove an assumed window, but does
not establish the real one. Present the bytes as reported and say the window is the API's own.

**3. `tokens` carries RAW LOG LINE FRAGMENTS and is never stored.** Live values include internal
hostnames and message bodies. It is stripped at the one seam every record passes through, and a test
asserts no record leaving this module carries it.

## Why aggregates, not records

One stack returned 222 recommendations; four stacks between them carried 520. Storing them would put
customer log-pattern detail in an S3 view for no question anybody asks. The stack summary plus a small
top-by-pending sample answers everything the dashboards show.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence

from collector.sources.stack_catalog import validated_base_url

if TYPE_CHECKING:
    from collector.httpclient import ReadOnlyClient

PLUGIN = "grafana-adaptivelogs-app"
PATH = f"api/plugin-proxy/{PLUGIN}/recommendations"

# Reasons a stack produced nothing. Shared vocabulary with `sources/assistant.py` on purpose: the repair
# for each is the same wherever it appears, and `403` vs `401` are different repairs (role vs token).
NO_CREDENTIAL = "no_credential"
UNAUTHORISED = "token_401"
FORBIDDEN = "forbidden_403"
PLUGIN_ABSENT = "plugin_absent_404"
HTTP_ERROR = "http_error"
TRANSPORT_ERROR = "transport_error"

# RBAC is cached, and a plugin-proxy 403 has already been observed as transient on a fully provisioned
# stack. One re-attempt, and only for statuses that can plausibly change in seconds - 401 (wrong token)
# and 404 (plugin not installed) never do, so retrying them just doubles the sweep.
RETRY_STATUSES = frozenset({403, 408, 425, 429, 500, 502, 503, 504, 520, 521, 522, 523, 524})
RETRY_DELAY = 3.0

# How many patterns to keep per stack for the drill-down table. Ranked by pending bytes, so the tail is
# rounding error against the head: one large pattern can dominate the captured total.
SAMPLE = 10

# Never leaves this module. Raw log-line fragments including internal hostnames.
DROPPED_FIELDS = ("tokens",)


def strip(record: Mapping[str, Any]) -> dict[str, Any]:
    """One recommendation without the fields that must not be stored."""
    return {k: v for k, v in record.items() if k not in DROPPED_FIELDS}


def pending_bytes(record: Mapping[str, Any]) -> float:
    """Bytes the recommendation would additionally drop, over the API's own unstated window.

    `max(0, ...)` because a configured rate ABOVE the recommended one is a stack that has been more
    aggressive than Adaptive Logs advises. That is not a negative saving to be netted off against a real
    one; it is simply nothing pending, and letting it go negative would understate the estate total.
    """
    rec = record.get("recommended_drop_rate") or 0
    cur = record.get("configured_drop_rate") or 0
    return (record.get("volume") or 0) * max(0, rec - cur) / 100.0


def is_pending(record: Mapping[str, Any]) -> bool:
    return (record.get("recommended_drop_rate") or 0) > (record.get("configured_drop_rate") or 0)


def is_unqueried(record: Mapping[str, Any]) -> bool:
    """Nobody has queried these lines, so dropping them needs no review conversation.

    Same reasoning as Adaptive Metrics' `remediable_series_unused`: reporting only the total invites
    "why has nobody done this", when most of a total is usually blocked on somebody confirming a
    dashboard still works.
    """
    return not (record.get("queried_lines") or 0)


def summarise(slug: str, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """One stack's aggregates. Never returns a rate - see the module docstring."""
    pend = [r for r in records if is_pending(r)]
    pend_bytes = sum(pending_bytes(r) for r in pend)
    unq = [r for r in pend if is_unqueried(r)]
    levels = sorted({str(level) for record in records for level in (record.get("levels") or [])})
    sample = sorted(pend, key=lambda r: -pending_bytes(r))[:SAMPLE]
    return {
        "available": True,
        "slug": slug,
        "recommendations": len(records),
        "pending": len(pend),
        # Already at or above the recommended rate. Counted, but its SAVING is unknowable here.
        "applied": sum(1 for r in records if (r.get("configured_drop_rate") or 0) > 0),
        "pending_bytes": pend_bytes,
        "pending_bytes_unqueried": sum(pending_bytes(r) for r in unq),
        "pending_unqueried": len(unq),
        "locked": sum(1 for r in records if r.get("locked")),
        "superseded": sum(1 for r in records if r.get("superseded")),
        "levels": levels,
        "sample": [
            {
                "pattern_levels": sorted(str(level) for level in (r.get("levels") or [])),
                "volume_bytes": r.get("volume") or 0,
                "ingested_lines": r.get("ingested_lines") or 0,
                "queried_lines": r.get("queried_lines") or 0,
                "configured_drop_rate": r.get("configured_drop_rate") or 0,
                "recommended_drop_rate": r.get("recommended_drop_rate") or 0,
                "pending_bytes": pending_bytes(r),
            }
            for r in sample
        ],
    }


def unavailable(slug: str, reason: str, detail: str = "") -> dict[str, Any]:
    return {"available": False, "slug": slug, "reason": reason, "detail": detail}


def _reason_for(status: int) -> str:
    return {401: UNAUTHORISED, 403: FORBIDDEN, 404: PLUGIN_ABSENT}.get(status, HTTP_ERROR)


def probe_stack(
    client: ReadOnlyClient,
    stack: Mapping[str, Any],
    token: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """One GET. Returns the stack's aggregates, or an `available: False` record saying why."""
    slug = str(stack.get("slug") or "")
    base, error = validated_base_url(stack)
    if error:
        return error
    url = f"{base}/{PATH}"
    resp = client.get(url, bearer=token)
    if not resp.ok and resp.status in RETRY_STATUSES:
        sleep(RETRY_DELAY)
        resp = client.get(url, bearer=token)
    if not resp.ok:
        return unavailable(slug, _reason_for(resp.status), f"HTTP {resp.status}")
    body = resp.json()
    if not isinstance(body, list):
        # A 200 that is not a list is not an empty estate, it is an unexpected contract. Saying
        # "0 recommendations" here would be a confident wrong answer of exactly the kind this
        # project keeps finding.
        return unavailable(slug, HTTP_ERROR, f"expected a list, got {type(body).__name__}")
    return summarise(slug, [strip(r) for r in body])


def probe_all(
    client: ReadOnlyClient,
    stacks: Sequence[Mapping[str, Any]],
    credentials: Mapping[str, Mapping[str, Any]],
    *,
    on_error: Callable[[str, str], None] | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """Iterate the LIVE INVENTORY and look each credential up (CLAUDE.md golden rule).

    A stack that appeared this morning gets a row saying `no_credential` until the daily provisioner
    reaches it; a stack that has left the estate gets no row whatever the credential store still holds.
    """
    out: dict[str, Any] = {}

    def one(stack: Mapping[str, Any]) -> None:
        slug = str(stack.get("slug") or "")
        if not slug:
            return
        if stack.get("status") == "paused":
            return
        record = credentials.get(slug) or {}
        token = str(record.get("token") or "")
        if not token:
            out[slug] = unavailable(slug, NO_CREDENTIAL,
                                    "no stored token - the daily provisioner has not reached it yet")
            return
        try:
            out[slug] = probe_stack(client, stack, token, sleep=sleep)
        except Exception as exc:  # noqa: BLE001 - one stack must never fail the sweep
            out[slug] = unavailable(slug, TRANSPORT_ERROR, f"{type(exc).__name__}: {exc}")
            if on_error:
                on_error(slug, f"adaptive_logs: {type(exc).__name__}")

    with ThreadPoolExecutor(max_workers=12) as pool:
        list(pool.map(one, stacks))
    return out
