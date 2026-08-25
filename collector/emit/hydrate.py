"""Cross-tier input hydration  -  the fix for tiers overwriting each other's views (PLAN 16.1).

## The defect this exists to prevent

Every tier called `compose.build_all` with only the inputs *it* had gathered, and then wrote **all 31
views** to S3. The pillars are honest about a missing input  -  they emit `None` and say "needs a T3 scan"
rather than a zero  -  but honesty per-run is not honesty on the dashboard, because the next tier's write
lands on top of the last one's. So the hourly T1, holding inventory alone, flattened nine views that only
T3 can compute:

    cost, cost_summary, risk, risk_admin_sprawl, risk_delete_protection,
    risk_summary, usage_summary, value_benchmarks, value_summary

Measured on the live bucket: `cost_summary` read "0 of 269 scannable" measured for Adaptive and zero
recommendations, while `cost_adaptive_headroom` beside it  -  written by T3 and *not* produced by T1, so
never overwritten  -  listed 114 stacks and ~36k pending recommendations. Two panels on one dashboard,
both live, disagreeing by the entire finding. A customer reading the summary would conclude the estate
has no Adaptive Metrics headroom at all.

**A view that renders a confident zero is worse than one that renders blank**, which is the same
principle `carry.py` was written for, one layer out.

## Why per-view tier ownership is not sufficient

The obvious fix  -  declare an owning tier per view and let lower tiers skip it  -  cannot work, because
two views need inputs that **no single tier gathers**:

- `risk_summary` needs `access_policies` (T1) **and** `stack_detail` (T2) **and** `dataplane` (T3).
- `maturity_owners` needs `stack_detail` (T2) **and** `dataplane` (T3).

Under tier ownership, whichever tier owns `risk_summary` still publishes it wrong. `maturity_owners`
is the proof this was already biting: no production tier can build it, so the copy on the bucket was a
**2-row artifact from a `--limit 2` hand-run**  -  its own meta said `stacks_total: 2`  -  while the real
answer is 268 stacks. It had sat there for two days looking like a finding about the organisation having almost no
discoverable stack ownership.

## The mechanism

Each tier gathers what it can, then **hydrates the rest from the other tiers' `scans/<tier>/latest.json`**
 -  the same S3-read pattern T4 already uses to diff. Every tier then composes the *complete* input set and
writes a complete, self-consistent view set.

Hydration is not a licence to present stale data as fresh. Two guards:

1. **`MAX_INPUT_AGE`**  -  an input older than the cap is refused, exactly as `carry.carry_forward`
   refuses stale state. It is deliberately the same constant, so the platform has ONE staleness story
   rather than two that can drift apart.
2. **A view whose inputs are not satisfied is WITHHELD, never written.** `VIEW_INPUTS` declares what
   each view needs and `filter_views` drops the rest, so the previous good copy survives on the bucket
   with its own older `generated_at`  -  visibly stale instead of silently wrong.

Provenance rides in every view's `meta.inputs`, so a panel can show per-input freshness. That replaces
the banner's old single "Data age", which read T1's timestamp on all eight dashboards and therefore
claimed hourly freshness for figures that came from the 6-hourly tier.
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
from typing import Any, Callable, Mapping

from collector.emit import s3 as s3emit
from collector.emit.carry import MAX_CARRY_AGE

# One cap for every hydrated input, shared with carry-forward on purpose (see the module docstring).
MAX_INPUT_AGE = MAX_CARRY_AGE

# Which tier natively gathers each optional input. `stacks` (inventory) is deliberately absent: it is
# gathered by T1, T2 and T3 alike and is never hydrated, because a tier with no inventory has nothing
# to compose at all.
INPUT_OWNER: dict[str, str] = {
    "access_policies": "t1",
    # One org-level gcom membership response. T1 owns it because it is control-plane inventory and
    # costs one GET for the whole org. A failed owner read is never hydrated from T1's previous run.
    "org_members": "t1",
    "stack_detail": "t2",
    # Service-account inventory has its own availability and request path. Keeping it inside
    # `stack_detail` made a successful user/plugin scan mask a total failure of this source.
    "service_accounts": "t2",
    "dataplane": "t3",
    # Per-stack Assistant reads (PLAN 17E). T2's second gatherer, and it is why hydration matters for
    # Pillar I: T2 runs daily, the dashboards default to a 6-hour window, so without T1 hydrating this
    # every AI panel would have at most one sample in range  -  the same defect PLAN 16.1 fixed for T2's
    # identity detail.
    "assistant": "t2",
    # Per-stack usage-insights reads. T2's third gatherer, and hydrated for the same reason as
    # `assistant`: it is measured daily, the dashboards default to a shorter window, and without
    # hydration every Pillar J panel would have at most one sample in range.
    "insights": "t2",
    # Fleet Management, moved out of the 6-hourly `dataplane` input to the HOURLY tier (PLAN 18.15).
    # A collector fleet changes by the minute - one stack moved 831 -> 1,791 -> 2,302 -> 1,906
    # registrations inside two days - so a 6-hourly reading was a snapshot of something already gone.
    # It costs one Connect-RPC pair per stack against per-stack FM hosts, which share no rate limit with
    # gcom.
    "fleet": "t1",
    # Adaptive Logs recommendations, read through each stack's own app-plugin proxy with the per-stack
    # reader token (PLAN 18.16). T2's fourth gatherer, and daily is the right cadence: these are
    # aggregate pattern recommendations, not events, and a full estate sweep is 269 requests against 269
    # DIFFERENT hosts, so it shares no rate limit with gcom. Hydrated into T1 for the usual reason - the
    # dashboards default to a 6-hour window and a daily input would otherwise have at most one sample.
    "adaptive_logs": "t2",
    # Public-dashboard ENUMERATION per stack (PLAN 18.17). T2's fifth gatherer, one GET per stack against
    # each stack's own API with the per-stack reader token - measured 269 stacks in 94s. Daily is right:
    # this is a compliance check against a policy of zero, and the remediation conversation is measured
    # in days, not minutes.
    "public_dashboards": "t2",
    # Alert-rule to contact-point routing inventory. A separate daily stack-local source: neither gcom
    # detail nor Grafana's org usage datasource can prove whether a rule inherits or names a receiver.
    "alert_routing": "t2",
    # Stage 19 identity-bearing S3 views. Each combines a stack-local catalogue with the matching
    # usage-insights observation; neither emits metric labels for dashboard or datasource identity.
    "dashboard_inventory": "t2",
    "datasource_query_cost": "t2",
    # Daily, atomic four-signal label inventory. Names stay in the hydrated S3 input and never become
    # metric labels; Pillar K derives only bounded counts and enums from it.
    "signal_inventory": "t2",
}

# What each view actually needs, beyond inventory.
#
# DERIVED, NOT ASSERTED. This table was produced by composing all eight subsets of the three optional
# inputs against a real scan and recording, per view, the minimal subset whose output is byte-identical
# to the full build  -  `tests/test_hydrate.py::ViewInputsAreDerivedNotAssumed` re-derives it from
# fixtures and fails if the declaration drifts from what the pillars really do. Hand-maintaining it
# would reintroduce the defect the module exists to fix: a view quietly needing a new input, still
# being written by a tier that lacks it.
VIEW_INPUTS: dict[str, frozenset[str]] = {
    # Pillar J. Every one needs the per-stack usage-insights sweep; none can be computed without it,
    # so all six are withheld rather than published as zeros by a tier that did not gather it.
    "insights_dashboard_usage": frozenset({"insights"}),
    "insights_public_dashboards": frozenset({"insights"}),
    "insights_top_dashboards": frozenset({"insights"}),
    "insights_datasource_types": frozenset({"insights"}),
    "insights_coverage": frozenset({"insights"}),
    "insights_summary": frozenset({"insights"}),
    "insights_dashboard_opening_31d": frozenset({"dashboard_inventory"}),
    "insights_datasource_query_cost": frozenset({"datasource_query_cost"}),
    # Pillar K. Derived from the compose fixture: the named service register includes explicit
    # dashboard tags and alert-rule labels, so all three inputs are required. Every other asset view
    # is a projection of the atomic four-signal inventory alone.
    "coverage_service_register": frozenset({
        "signal_inventory", "dashboard_inventory", "alert_routing",
    }),
    "coverage_technology_register": frozenset({"signal_inventory"}),
    "coverage_metric_name_register": frozenset({"signal_inventory"}),
    "coverage_cluster_register": frozenset({"signal_inventory"}),
    "coverage_legacy_service_register": frozenset({"signal_inventory"}),
    "coverage_summary": frozenset({"signal_inventory"}),
    "cost": frozenset({"dataplane"}),
    "cost_adaptive_headroom": frozenset({"dataplane"}),
    "cost_adaptive_metric_recommendations": frozenset({"dataplane"}),
    # Adaptive LOGS, not metrics - a different input from a different tier. DERIVED by the test, not
    # reasoned about: it needs `adaptive_logs` alone and notably NOT `dataplane`, so a T1 run that has
    # hydrated the daily logs sweep publishes it correctly even when T3 has never run.
    "cost_adaptive_logs": frozenset({"adaptive_logs"}),
    "risk_public_dashboards": frozenset({"public_dashboards"}),
    "risk_alert_routing": frozenset({"alert_routing"}),
    "risk_alert_routing_findings": frozenset({"alert_routing"}),
    "cost_cardinality_outliers": frozenset({"dataplane"}),
    "cost_summary": frozenset({"dataplane"}),
    "maturity": frozenset({"dataplane"}),
    "maturity_dimensions": frozenset({"dataplane"}),
    "maturity_owners": frozenset({"dataplane", "stack_detail"}),
    "maturity_rubric": frozenset({"dataplane"}),
    "maturity_summary": frozenset({"dataplane"}),
    "risk": frozenset({"fleet", "service_accounts"}),
    "risk_access_policies": frozenset({"access_policies"}),
    "risk_org_members": frozenset({"org_members"}),
    # These three are narrow projections, so only the source whose fields they display can withhold
    # them. Admin and delete-protection are inventory-only; Fleet dead needs Fleet alone.
    "risk_fleet_dead": frozenset({"fleet"}),
    "risk_fleet_attributes": frozenset({"fleet"}),
    "risk_fleet_pipelines": frozenset({"fleet"}),
    "risk_plugin_drift": frozenset({"stack_detail"}),
    "risk_service_accounts": frozenset({"service_accounts"}),
    "risk_summary": frozenset({"access_policies", "dataplane", "service_accounts"}),
    "usage_summary": frozenset({"stack_detail"}),
    "usage_user_recency": frozenset({"stack_detail"}),
    "ai_assistant": frozenset({"assistant"}),
    "ai_category_surface": frozenset({"assistant"}),
    "ai_config_disabled": frozenset({"assistant"}),
    "ai_credential_coverage": frozenset({"assistant"}),
    "ai_enablement_gap": frozenset({"assistant"}),
    "ai_mcp_auth_failed": frozenset({"assistant"}),
    "ai_summary": frozenset({"assistant"}),
    "ai_tenant_config": frozenset({"assistant"}),
    "ai_token_outliers": frozenset({"assistant"}),
    "value_benchmarks": frozenset({"dataplane"}),
    "value_savings": frozenset({"dataplane"}),
    "value_summary": frozenset({"dataplane"}),
}


class Provenance(dict):
    """Per-input origin and age. A dict so it serialises straight into the view meta."""

    def satisfied(self, name: str) -> bool:
        entry = self.get(name) or {}
        return bool(entry.get("available")) and not entry.get("stale")

    def unsatisfied(self) -> list[str]:
        return sorted(n for n in self if not self.satisfied(n))


def _load_latest(tier: str, bucket: str) -> dict[str, Any] | None:
    """Read `scans/<tier>/latest.json`. A missing or unreadable object is not an error.

    A tier that has never run has no `latest.json`, which is the normal state of a fresh deployment.
    Failing the hydrating tier for it would mean T1 could not run until T2 and T3 both had.
    """
    uri = f"s3://{bucket}/scans/{tier}/latest.json"
    proc = subprocess.run(
        ["aws", "s3", "cp", uri, "-", "--region", s3emit.REGION, "--only-show-errors"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def _age(generated_at: Any, now: dt.datetime) -> dt.timedelta | None:
    """`None` for anything unparseable  -  treated as infinitely old by the caller.

    A scan whose timestamp cannot be read must not be trusted as fresh. Same rule as
    `carry.carry_forward`, where a bad timestamp refuses the carry rather than defaulting to zero age.
    """
    try:
        stamp = dt.datetime.fromisoformat(str(generated_at))
    except (TypeError, ValueError):
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    return now - stamp


def hydrate(
    tier: str,
    own: dict[str, Any],
    *,
    unavailable: Mapping[str, Mapping[str, Any] | str] | None = None,
    bucket: str = s3emit.BUCKET,
    now: dt.datetime | None = None,
    max_age: dt.timedelta = MAX_INPUT_AGE,
    loader: Callable[[str, str], dict[str, Any] | None] = _load_latest,
) -> tuple[dict[str, Any], Provenance]:
    """Fill in the optional inputs `tier` did not gather itself.

    `own` holds whatever this run measured *and accepted for publication*. `unavailable` records inputs
    the owning tier did gather but refused because their independently measured coverage was below the
    publication floor. Keeping those separate matters: an empty credential store is unavailable, while
    one successful stack out of an estate is partial; neither is permission to compose an estate total.

    Anything simply absent or falsy is fetched from the owning tier's latest scan. Returns the merged
    inputs (suitable for `compose.build_all(**inputs)`) and the provenance record.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    inputs: dict[str, Any] = {}
    prov = Provenance()
    unavailable = unavailable or {}

    for name, owner in sorted(INPUT_OWNER.items()):
        if name in unavailable:
            detail = unavailable[name]
            if isinstance(detail, Mapping):
                state = str(detail.get("state") or "unavailable")
                reason = str(detail.get("reason") or state)
            else:
                state = "unavailable"
                reason = str(detail)
            prov[name] = {
                "available": False, "source": "own", "tier": tier,
                "age_seconds": None, "stale": False,
                "state": state, "reason": reason,
            }
            continue
        if own.get(name):
            inputs[name] = own[name]
            prov[name] = {
                "available": True, "source": "own", "tier": tier,
                "age_seconds": 0.0, "stale": False,
            }
            continue

        scan = loader(owner, bucket) if owner != tier else None
        if not scan:
            # A tier cannot hydrate from ITSELF: if this run did not gather the input, its own
            # latest.json does not have it either, and reading last run's copy back would make a
            # broken gatherer look healthy for ever.
            prov[name] = {
                "available": False, "source": "missing", "tier": owner,
                "age_seconds": None, "stale": True,
                "reason": f"no readable scans/{owner}/latest.json",
            }
            continue

        meta = scan.get("meta") or {}
        source_health = (meta.get("sources") or {}).get(name)
        age = _age(meta.get("generated_at"), now)
        if isinstance(source_health, Mapping) and source_health.get("healthy") is False:
            def _count(value: Any) -> int:
                try:
                    return int(value or 0)
                except (TypeError, ValueError):
                    return 0

            measured = _count(source_health.get("available"))
            expected = _count(source_health.get("expected"))
            state = "partial" if measured else "unavailable"
            prov[name] = {
                "available": False, "source": "hydrated", "tier": owner,
                "age_seconds": None if age is None else age.total_seconds(), "stale": False,
                "state": state,
                "reason": f"owner scan rejected {state} input: {measured} of {expected} available",
            }
            continue

        payload = (scan.get("data") or {}).get(name)
        if not payload:
            prov[name] = {
                "available": False, "source": "missing", "tier": owner,
                "age_seconds": None if age is None else age.total_seconds(), "stale": True,
                "reason": f"scans/{owner}/latest.json carries no {name!r}",
            }
            continue
        if age is None or age > max_age:
            prov[name] = {
                "available": False, "source": "stale", "tier": owner,
                "age_seconds": None if age is None else age.total_seconds(), "stale": True,
                "reason": (f"unparseable generated_at" if age is None else
                           f"{age.total_seconds() / 3600:.1f}h old, cap is "
                           f"{max_age.total_seconds() / 3600:.0f}h"),
            }
            continue

        inputs[name] = payload
        prov[name] = {
            "available": True, "source": "hydrated", "tier": owner,
            "age_seconds": age.total_seconds(), "stale": False,
        }

    return inputs, prov


def filter_views(
    views: dict[str, list[Any]], prov: Provenance
) -> tuple[dict[str, list[Any]], dict[str, str]]:
    """Split composed views into the ones safe to publish and the ones to withhold.

    Withholding leaves the previous copy on the bucket. That is the point: an older `generated_at` on a
    correct table beats a current one on a table of zeros, and the freshness panels make the age
    visible. A view absent from `VIEW_INPUTS` needs inventory only and always publishes.
    """
    keep: dict[str, list[Any]] = {}
    withheld: dict[str, str] = {}
    for name, rows in views.items():
        missing = sorted(n for n in VIEW_INPUTS.get(name, frozenset()) if not prov.satisfied(n))
        if missing:
            reasons = "; ".join(
                f"{n}: {(prov.get(n) or {}).get('reason', 'unavailable')}" for n in missing
            )
            withheld[name] = reasons
        else:
            keep[name] = rows
    return keep, withheld


def report_metrics(prov: Provenance, tier: str) -> list[tuple[str, dict[str, str], float]]:
    """Per-input age as a gauge, so input staleness is alertable and panellable.

    Emitted with the age of the input, NOT of the tier that consumed it. An unavailable input emits no
    age at all rather than a zero, because a zero would read as "gathered just now"  -  the same reason
    `carry.report_metrics` omits it.
    """
    out: list[tuple[str, dict[str, str], float]] = []
    for name, entry in sorted(prov.items()):
        out.append((
            "gcinsight_input_available",
            {"tier": tier, "input": name},
            1.0 if entry.get("available") else 0.0,
        ))
        # `age_seconds` on an unavailable provenance entry is the age of the failed owner envelope,
        # not the age of usable data. Emitting it made a freshly failed scan look like fresh input.
        if entry.get("available") and entry.get("age_seconds") is not None:
            out.append((
                "gcinsight_input_age_seconds",
                {"tier": tier, "input": name},
                float(entry["age_seconds"]),
            ))
    return out


def summarise(prov: Provenance, withheld: dict[str, str]) -> str:
    parts = []
    for name, entry in sorted(prov.items()):
        if entry.get("available"):
            age = entry.get("age_seconds") or 0.0
            parts.append(f"{name}={entry['source']}"
                         + (f"({age / 3600:.1f}h)" if entry["source"] == "hydrated" else ""))
        else:
            parts.append(f"{name}=UNAVAILABLE({entry.get('reason', '?')})")
    line = "inputs: " + ", ".join(parts)
    if withheld:
        line += f"\nwithheld {len(withheld)} view(s): " + ", ".join(sorted(withheld))
    return line
