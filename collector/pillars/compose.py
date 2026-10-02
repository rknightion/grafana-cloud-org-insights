"""Run every pillar the available data supports, and gate the result (PLAN 4.x, 5.2).

One entry point so a tier does not have to know which pillars it can feed. Each pillar decides for
itself what it can compute from what it is given, and returns `None`-shaped gaps rather than zeros.

**Re-emitting the same series from more than one tier is intended, not a bug.** T1 runs hourly with
inventory only and T3 runs weekly with the data plane too, so both emit the Pillar A and C inventory
rollups. That is the same mechanism PLAN 5.3 relies on: a Mimir series with one sample a week is only
resolvable inside the 5-minute lookback-delta, so the hourly tier re-emitting it is what stops every
weekly gauge rendering "No data" for 99.95% of the week.

What is *not* allowed is the same series twice **within one batch** - that would publish whichever
sample the encoder wrote last. `guard.check_no_duplicates` enforces it here, at the composition point.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from collector.coverage import Coverage
from collector.emit import guard
from collector.pillars import (
    adaptive_traces as adaptive_traces_pillar,
    ai,
    cost,
    coverage as coverage_pillar,
    estate,
    label_risk as label_risk_pillar,
    maturity,
    producing_signals,
    retention,
    risk,
    usage,
    value,
)
# Aliased: the kwarg is `insights`, matching the hydrated input key so `**inputs` works.
from collector.pillars import insights as insights_pillar
from collector.pillars import insights_inventory
from collector.pillars import slo as slo_pillar

Metrics = list[tuple[str, dict[str, str], float]]
Views = dict[str, list[dict[str, Any]]]


def _display_number(v: Any) -> Any:
    """A whole number stored as a float becomes an int.

    Grafana renders a large float in scientific notation, so a remediable-series count arrives on the
    dashboard as `5.783425e+06`. Nobody reads that as 5.8 million. Converting integral floats to int
    fixes it at the one place every view passes through, rather than in each pillar that happens to
    sum a float field.

    Deliberately narrow: a genuinely fractional value is left EXACTLY as the pillar produced it.
    Rounding here would quietly flatten a ratio like 0.446, and a tiny volume such as 8.9e-07 GB would
    round to zero, which turns "almost nothing" into "nothing".
    """
    if isinstance(v, bool) or not isinstance(v, float):
        return v
    if v != v or v in (float("inf"), float("-inf")):    # NaN / inf survive untouched
        return v
    return int(v) if v.is_integer() else v


def _display(views: Views) -> Views:
    return {
        name: [{k: _display_number(val) for k, val in row.items()} for row in rows]
        for name, rows in views.items()
    }


def build_all(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    *,
    dataplane: dict[str, Any] | None = None,
    stack_detail: dict[str, Any] | None = None,
    service_accounts: dict[str, Any] | None = None,
    access_policies: list[dict[str, Any]] | None = None,
    assistant: dict[str, Any] | None = None,
    gap_first_seen: dict[str, str] | None = None,
    ratecard: Any | None = None,
    insights: dict[str, Any] | None = None,
    fleet: dict[str, Any] | None = None,
    adaptive_logs: dict[str, Any] | None = None,
    adaptive_traces: dict[str, Any] | None = None,
    public_dashboards: dict[str, Any] | None = None,
    alert_routing: dict[str, Any] | None = None,
    org_members: dict[str, Any] | None = None,
    dashboard_inventory: dict[str, Any] | None = None,
    datasource_query_cost: dict[str, Any] | None = None,
    # Gathered and hydrated in GCI-0008.04; consumed by the single Pillar K wiring pass in .05.
    signal_inventory: dict[str, Any] | None = None,
    capability_adoption: dict[str, Any] | None = None,
    slo_inventory: dict[str, Any] | None = None,
    loki_config: dict[str, Any] | None = None,
    label_risk: dict[str, Any] | None = None,
    expected_retention_policy: tuple[dict[str, str], ...] = (),
    fleet_default_scrape_interval_seconds: float = 60.0,
    score_weights: dict[str, float] | None = None,
    now: dt.datetime | None = None,
) -> tuple[Metrics, Views, dict[str, dict[str, Any]]]:
    """Compose every pillar, then gate labels and duplicates before anything can be emitted."""
    metrics: Metrics = []
    views: Views = {}

    for pillar_metrics, pillar_views in (
        estate.build(stacks, coverage, now=now),
        cost.build(stacks, coverage, dataplane, adaptive_logs),
        usage.build(stacks, coverage, stack_detail, now=now),
        maturity.build(stacks, coverage, dataplane, stack_detail),
        risk.build(stacks, coverage, dataplane, stack_detail, access_policies, fleet=fleet,
                   public_dashboards=public_dashboards, service_accounts=service_accounts,
                   alert_routing=alert_routing, org_members=org_members,
                   fleet_default_scrape_interval_seconds=fleet_default_scrape_interval_seconds,
                   now=now),
        retention.build(
            stacks,
            coverage,
            loki_config,
            expected_policy=expected_retention_policy,
        ),
        value.build(stacks, coverage, dataplane, ratecard=ratecard),
        ai.build(stacks, coverage, assistant, gap_first_seen=gap_first_seen, now=now),
        insights_pillar.build(stacks, coverage, insights),
        insights_inventory.build(
            stacks,
            dashboard_inventory=dashboard_inventory,
            datasource_query_cost=datasource_query_cost,
        ),
        coverage_pillar.build(
            stacks, signal_inventory,
            dashboard_inventory=dashboard_inventory,
            alert_routing=alert_routing,
            capability_adoption=capability_adoption,
            score_weights=score_weights,
        ),
        producing_signals.build(stacks, capability_adoption),
        adaptive_traces_pillar.build(stacks, adaptive_traces),
        slo_pillar.build(stacks, slo_inventory),
        label_risk_pillar.build(stacks, label_risk),
    ):
        metrics.extend(pillar_metrics)
        for name, rows in pillar_views.items():
            if name in views:
                raise ValueError(f"two pillars produced a view named {name!r}")
            views[name] = rows

    # Both gates are errors, not warnings (SPEC §10.3).
    guard.check_all(metrics)
    guard.check_no_duplicates(metrics)
    # Independent of rows: a measured, empty subset is not proof of a complete zero estate.
    rules_cov = cost.rules_coverage(stacks, dataplane)
    view_coverage = {name: dict(rules_cov) for name in (
        "cost_summary", "cost_adaptive_headroom", "cost_adaptive_metric_recommendations",
    ) if name in views}
    if "value_savings" in views:
        value_scope = [s for s in stacks if s.get("hmInstancePromUrl")]
        view_coverage["value_savings"] = cost.rules_coverage(value_scope, dataplane)
    return metrics, _display(views), view_coverage
