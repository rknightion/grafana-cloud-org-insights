"""Resolve a usage-insights `instance_id` to its stack and signal.

The highest-bug-risk code in the collector, and the traps are all counter-intuitive (SPEC §6,
`docs/traps.md`):

- **Stack resolution is unambiguous by number.** Verified: zero cross-stack collisions across all
  seven inventory id fields in the captured estate. So a bare
  `instance_id` always identifies exactly one stack, and `instance_type` is never needed to find it.
- **`instance_type` is the ONLY source of the signal.** Never infer it from which field matched. A
  stack's `id`, `hpInstanceId` and `agentManagementInstanceId` are the *same number* on 271/271
  stacks, so the field a number matches does not identify a signal.
- **`hmInstanceGraphiteId` is a METRICS id.** Verified: 139 ids matched only that field and every one
  is labelled `instance_type="metrics"`. A metrics-type stack contributes two ids, prom and graphite,
  both on the metrics tenant. Treating that field as a Graphite stream would report Graphite activity
  on ~136 stacks on an estate using Graphite on 2.
- **Only five `instance_type` values exist.** No `graphite` stream, no `profiles` stream. An unknown
  type is counted and surfaced, never silently dropped.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping

# The five values observed in usage-insights. Anything else is a change we must notice.
KNOWN_SIGNALS = frozenset({"alerts", "grafana", "logs", "metrics", "traces"})

# Inventory fields that can carry an instance id, used ONLY for stack resolution.
ID_FIELDS = (
    "id",
    "hmInstancePromId",
    "hmInstanceGraphiteId",
    "hlInstanceId",
    "htInstanceId",
    "hpInstanceId",
    "amInstanceId",
)


@dataclass(frozen=True)
class Resolved:
    stack: str
    region: str
    cluster: str
    signal: str


@dataclass
class ResolverStats:
    resolved: int = 0
    unknown_instance: Counter = field(default_factory=Counter)
    unknown_signal: Counter = field(default_factory=Counter)
    ambiguous: Counter = field(default_factory=Counter)

    def as_dict(self) -> dict[str, object]:
        return {
            "resolved": self.resolved,
            "unknown_instance_ids": sum(self.unknown_instance.values()),
            "unknown_signals": dict(self.unknown_signal),
            "ambiguous_instance_ids": dict(self.ambiguous),
        }


class InstanceResolver:
    def __init__(self, stacks: Iterable[Mapping[str, object]]) -> None:
        self._by_id: dict[str, list[tuple[str, str, str]]] = {}
        for stack in stacks:
            slug = str(stack["slug"])
            region = str(stack.get("regionSlug") or "")
            cluster = str(stack.get("clusterSlug") or "")
            for field_name in ID_FIELDS:
                raw = stack.get(field_name)
                if not raw:
                    continue
                entry = (slug, region, cluster)
                bucket = self._by_id.setdefault(str(raw), [])
                if entry not in bucket:
                    bucket.append(entry)
        self.stats = ResolverStats()

    def cross_stack_collisions(self) -> dict[str, list[str]]:
        """Instance ids claimed by more than one stack. Verified empty on the 2026-08-17 inventory."""
        return {
            iid: sorted({slug for slug, _, _ in entries})
            for iid, entries in self._by_id.items()
            if len({slug for slug, _, _ in entries}) > 1
        }

    def resolve(self, instance_id: object, instance_type: object) -> Resolved | None:
        iid = str(instance_id)
        signal = str(instance_type)

        entries = self._by_id.get(iid)
        if not entries:
            self.stats.unknown_instance[iid] += 1
            return None

        slugs = {slug for slug, _, _ in entries}
        if len(slugs) > 1:
            # Never pick the first match: k6OrgId sits inside the prom/graphite numeric range, so a
            # foreign id could plausibly land here. Count it and refuse to guess.
            self.stats.ambiguous[iid] += 1
            return None

        if signal not in KNOWN_SIGNALS:
            self.stats.unknown_signal[signal] += 1
            return None

        slug, region, cluster = entries[0]
        self.stats.resolved += 1
        return Resolved(stack=slug, region=region, cluster=cluster, signal=signal)


# --- Insight-host resolution (PLAN 2.4) ------------------------------------------------------------
#
# READ the host from the stack's datasource list. Never build it from `regionSlug` or `clusterSlug`.
#
# Measured over the 271-stack inventory, and this is why the rule is absolute:
#
#   * **`regionSlug` -> `clusterSlug` is not a function.** `prod-eu-west-2` maps to `prod-eu-west-4` on
#     127 stacks and to `prod-eu-west-2` on 45; `prod-us-east-0` maps to `prod-us-east-2` on 24 and to
#     itself on 5. No derivation from the region can exist even in principle.
#   * **158 of 271 stacks (58%) have the two slugs differ**, so region-derivation is wrong on the
#     majority of the estate.
#   * **The 7 legacy stacks cannot be munged at all** - `eu` (4, GCP) sits on cluster `prod-eu-west-0`
#     and `us-azure` (3, Azure) on `prod-us-central-7`. Neither region string contains its cluster.
#   * **One stack has TWO insight hosts on DIFFERENT slugs.** On `obs-hub-dev`, usage-insights is
#     `insight-logs-prod-eu-west-4` (cluster) while cardinality-management is
#     `insights-prod-eu-west-2` (region). There is no single "the insight host" to resolve.
#
# `insight_hosts()` deliberately takes only the datasource list, never the stack record: a function that
# cannot see `regionSlug` cannot be tempted to use it.

# Match on the NAME suffix, not the type. `grafanacloud-<slug>-alert-state-history` is also `type: loki`
# and today points at the same host, so a type-only match looks right until a stack where it does not -
# which surfaces as a silent read against the wrong tenant rather than an error.
USAGE_INSIGHTS_SUFFIX = "-usage-insights"
CARDINALITY_DS_TYPE = "grafanacloud-cardinality-datasource"


@dataclass(frozen=True)
class InsightHosts:
    """Resolved hosts for one stack. `None` means the datasource was absent - never a guess."""

    usage_insights: str | None = None
    cardinality: str | None = None


def insight_hosts(datasources: Iterable[Mapping[str, object]]) -> InsightHosts:
    """Resolve a stack's insight hosts from its datasource list.

    Returns `None` for anything not present rather than deriving a plausible host, because a wrong host
    answers HTTP 200 with zero streams - indistinguishable from a quiet stack.
    """
    usage = cardinality = None
    for ds in datasources or ():
        name = str(ds.get("name") or "")
        url = ds.get("url")
        if not url:
            continue
        if usage is None and name.endswith(USAGE_INSIGHTS_SUFFIX):
            usage = str(url)
        elif cardinality is None and str(ds.get("type") or "") == CARDINALITY_DS_TYPE:
            cardinality = str(url)
    return InsightHosts(usage_insights=usage, cardinality=cardinality)
