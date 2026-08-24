"""Fleet Management: collectors, pipelines, and which pipeline reaches which collector.

Split out of `dataplane.py` and moved to the HOURLY tier (PLAN 18.15). A collector fleet changes by the
minute - one stack went 831 -> 1,791 -> 2,302 -> 1,906 registrations inside a couple of days - so a
6-hourly reading of it was always a snapshot of something already gone.

## The defect this module exists to fix

`dataplane.fleet` returned `len(collectors)` and threw away `markedInactiveAt`. Measured across the 12
biggest FM stacks, 3,308 of the estate's 3,422 reported collectors: **1,035 alive, 2,273 dead. 68.7% of
the headline number was registrations for collectors that no longer exist.** Three stacks accounted for
almost all of it (92%, 82%, 81% dead) while nine others were essentially clean, so an estate-wide
average would have hidden it too.

The cause is ephemeral compute: a collector's id embeds its hostname
(`...-alloy-receiver-ip-100-67-25-4.us-west-2.compute.internal`), so every pod reschedule registers a
NEW collector and the old one is marked inactive. Fleet Management prunes them eventually, which is why
the number goes down as well as up - and why a rising collector count is not necessarily a growing fleet.

**`collectors` keeps its old meaning** (every registration FM returns) so the published series stays
continuous, and `collectors_active` / `collectors_inactive` are new alongside it. A metric that has been
wrong for weeks gets a correct sibling rather than a silent redefinition.

## Attributes: a deliberate subset

Collector records carry 11 attribute keys. Only the low-cardinality, fleet-shaped ones are kept -
version, platform, source, sourceVersion, os and collector type. Deliberately dropped: `cluster`,
`namespace`, `workloadName`, `collector.ID`. Those are per-workload identifiers, they are unbounded, and
`collector.ID` is a HOSTNAME - none of them belongs anywhere near a metric label, and none answers a
question this platform asks.
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Callable, Mapping, Sequence

from collector.sources import matchers as M
from collector.sources.dataplane import _connect_rpc, auth_for

LIST_COLLECTORS = "collector.v1.CollectorService/ListCollectors"
LIST_PIPELINES = "pipeline.v1.PipelineService/ListPipelines"

# Kept per collector, and each one is a closed set in practice: os is linux/windows/darwin, platform is
# kubernetes/docker/bare, source names the installer. Safe to aggregate, safe to trend.
KEPT_ATTRIBUTES = ("collector.version", "collector.os", "platform", "source", "sourceVersion")

# Present on the record but not under `attributes`.
KEPT_FIELDS = ("collectorType",)

# Never kept. `collector.ID` is a hostname; the rest are per-workload and unbounded.
DROPPED_ATTRIBUTES = ("collector.ID", "cluster", "namespace", "workloadName", "workloadType", "release")

# How many distinct values of one attribute to report per stack. A stack running one Alloy version has a
# one-row breakdown; a stack mid-upgrade has two or three. Beyond this it is not a fleet, it is drift,
# and the count is the finding rather than the list.
MAX_ATTRIBUTE_VALUES = 12


def _ts(value: Any) -> dt.datetime | None:
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed
    except ValueError:
        return None


def is_inactive(collector: Mapping[str, Any]) -> bool:
    """Has this registration been marked inactive and not come back?

    `markedInactiveAt` alone is not enough: a collector that was marked and then reported again has a
    LATER `updatedAt`, and counting it as dead would understate a fleet that is merely flapping.
    Measured on one estate: zero collectors had come back, so the comparison changes nothing today and
    prevents a wrong answer the first time one does.
    """
    marked = _ts(collector.get("markedInactiveAt"))
    if marked is None:
        return False
    updated = _ts(collector.get("updatedAt"))
    return updated is None or updated <= marked


def attribute_breakdown(collectors: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Value counts per kept attribute, over the collectors passed in.

    Call it with the ALIVE collectors: a version breakdown that includes dead registrations describes
    the fleet as it was, which is the same defect one level down.
    """
    out: dict[str, dict[str, int]] = {}
    for key in KEPT_ATTRIBUTES:
        counts: dict[str, int] = {}
        for c in collectors:
            value = str((c.get("attributes") or {}).get(key) or "unknown")
            counts[value] = counts.get(value, 0) + 1
        # Widest first, then bounded. The tail of a long list is noise; its LENGTH is the signal, and
        # `distinct` carries that separately so truncation never looks like the whole picture.
        top = dict(sorted(counts.items(), key=lambda kv: -kv[1])[:MAX_ATTRIBUTE_VALUES])
        out[key] = {"values": top, "distinct": len(counts)}
    counts = {}
    for c in collectors:
        value = str(c.get("collectorType") or "unknown")
        counts[value] = counts.get(value, 0) + 1
    out["collectorType"] = {"values": counts, "distinct": len(counts)}
    return out


def pipeline_record(
    pipeline: Mapping[str, Any], targeted: int | None, targeted_enabled: int
) -> dict[str, Any]:
    """One pipeline, without its `contents`.

    **`contents` is never kept.** It is the full Alloy configuration - kilobytes per pipeline, and it is
    the customer's own config including whatever they put in it. The shape of a pipeline is answered by
    its matchers and its source; the body is not this platform's business.
    """
    source = pipeline.get("source") or {}
    return {
        "name": pipeline.get("name"),
        "enabled": bool(pipeline.get("enabled")),
        "matchers": list(pipeline.get("matchers") or []),
        # SOURCE_TYPE_GRAFANA means Grafana generated it; an absent source means somebody wrote it.
        # That distinction is the difference between "onboarding created this" and "a team owns this".
        "source_type": source.get("type") or "user",
        "config_type": pipeline.get("config_type") or pipeline.get("configType"),
        "targeted": targeted,
        "targeted_enabled": targeted_enabled,
        "updated_at": pipeline.get("updatedAt"),
    }


def probe_stack(stack: Mapping[str, Any], cap: str) -> dict[str, Any]:
    """One stack's fleet. Read-only: both calls are Connect-RPC `List*` methods."""
    base = stack.get("agentManagementInstanceUrl")
    if not base:
        return {"available": False, "reason": "no_fm_url"}
    try:
        user, _ = auth_for(dict(stack), "fleet", cap)
    except KeyError:
        return {"available": False, "reason": "no_stack_id"}

    collectors = _connect_rpc(f"{base}/{LIST_COLLECTORS}", user, cap)
    if not isinstance(collectors, Mapping):
        return {"available": False, "reason": "invalid_collectors_response"}
    if "_http" in collectors:
        return {"available": False, "reason": "http_error", "http": collectors["_http"],
                "failed_rpc": "collectors"}
    # Protobuf JSON omits an empty repeated field, so a healthy empty List response is `{}`.
    # An explicitly present non-list value remains malformed and must not become a measured zero.
    raw_collectors = collectors.get("collectors", [])
    if not isinstance(raw_collectors, list) or any(
        not isinstance(record, Mapping) for record in raw_collectors
    ):
        return {"available": False, "reason": "invalid_collectors_response"}

    pipelines = _connect_rpc(f"{base}/{LIST_PIPELINES}", user, cap)
    if not isinstance(pipelines, Mapping):
        return {"available": False, "reason": "invalid_pipelines_response"}
    if "_http" in pipelines:
        return {"available": False, "reason": "http_error", "http": pipelines["_http"],
                "failed_rpc": "pipelines"}
    raw_pipelines = pipelines.get("pipelines", [])
    if not isinstance(raw_pipelines, list) or any(
        not isinstance(record, Mapping) for record in raw_pipelines
    ):
        return {"available": False, "reason": "invalid_pipelines_response"}

    clist = list(raw_collectors)
    plist = list(raw_pipelines)

    inactive = [c for c in clist if is_inactive(c)]
    alive = [c for c in clist if not is_inactive(c)]

    # Targeting is computed against the ALIVE fleet: a pipeline's reach over registrations that no
    # longer exist is not a fact about anything.
    reach = M.targets(plist, alive)
    pipe_rows = [
        pipeline_record(p, n, e)
        for p, n, e in zip(plist, reach["counts"], reach["enabled_counts"])
    ]

    return {
        "available": True,
        # Unchanged meaning, so the published series stays continuous.
        "collectors": len(clist),
        "collectors_active": len(alive),
        "collectors_inactive": len(inactive),
        "pipelines": len(plist),
        "pipelines_enabled": sum(1 for p in plist if p.get("enabled")),
        "pipelines_generated": sum(
            1 for p in plist if (p.get("source") or {}).get("type") == "SOURCE_TYPE_GRAFANA"),
        # FM configured and nothing LIVE registered. Against `alive`, not against every registration:
        # a stack whose collectors are all dead is the exact case the old check called healthy.
        "provisioned_but_empty": bool(plist) and not alive,
        "collectors_unmatched": reach["unmatched"],
        "matchers_unparsed": reach["unparsed"],
        "collector_versions": sorted({
            str((c.get("attributes") or {}).get("collector.version") or "?") for c in alive
        }),
        "attributes": attribute_breakdown(alive),
        "pipeline_detail": pipe_rows,
    }


def probe_all(
    stacks: Sequence[Mapping[str, Any]],
    cap: str,
    *,
    on_error: Callable[[str, str], None] | None = None,
) -> dict[str, dict[str, Any]]:
    """Sweep the LIVE inventory (CLAUDE.md golden rule), never a stored list of FM-enabled stacks."""
    out: dict[str, dict[str, Any]] = {}
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        if not slug:
            continue
        if stack.get("status") == "paused":
            continue
        try:
            out[slug] = probe_stack(stack, cap)
        except Exception as exc:  # noqa: BLE001 - one stack must never fail the sweep
            out[slug] = {"available": False, "reason": type(exc).__name__}
            if on_error:
                on_error(slug, f"fleet: {type(exc).__name__}")
    return out
