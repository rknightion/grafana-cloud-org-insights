"""Pillar F - business value, for a leadership audience read weekly (PLAN 4.6).

This stays a **live dashboard designed for weekly reading**, not a quarterly document. So
every number is one a platform lead can act on within a week, and nothing here is a projection.

**The savings figure is a real series reduction, and gets currency only with an explicit rate-card
basis.** The
remediable series count comes from the Adaptive recommendations themselves: `?verbose=true` returns a
`current_series_count` and a `recommended_series_count` per metric, and the sum of the differences is
what applying every recommendation would remove. Turning that into money needs the org's contracted
rate, which this code cannot infer - so `collector/ratecard.py` reads one if the deployment supplies
it, and without one the pillar reports the volume and says why there is no currency figure. A
`base_rate_only` card prices the collector's reduction and labels DPM excluded. A `dpm_aware` card uses
the documented 30-day p95 active-series / DPM regime in a live `grafanacloud-usage` panel; those inputs
do not become pipeline series, so this pillar's currency metrics remain absent on that basis.

**Money rules:** `billingActiveUsers` is the only user count valid for money, never
`currentActiveUsers`. Internal benchmarking uses median / p90 / worst, never a mean: one extreme stack
can otherwise define the estate-wide result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from collector.coverage import Coverage
from collector.pillars.maturity import RUBRIC_VERSION, score_stack
from collector.pillars.usage import SIGNAL_FIELDS

if TYPE_CHECKING:
    from collector.ratecard import RateCard

# **`usage.USAGE_FLOOR` (1,000) IS A SERIES COUNT AND MUST NOT BE APPLIED TO THE VOLUME-DENOMINATED SIGNALS.**
#
# This was the adoption bug. `SIGNAL_FIELDS` mixes two different units:
# * `hmInstancePromCurrentUsage` / `hmInstanceGraphiteCurrentUsage` count SERIES - estate max 3,164,653.
# * `hlInstanceCurrentUsage` / `htInstanceCurrentUsage` / `hpInstanceCurrentUsage` are VOLUMES - estate
# max **16.86** for logs and **1.08** for traces.
#
# A floor of 1,000 against a field whose estate-wide maximum is 16.86 can only ever return zero, so
# `value_adoption_ratio` published **logs 0% and traces 0%** - on a dashboard whose own panels showed both
# near-universal, and whose own panel description said so. The floor was borrowed from the OTLP
# synthetic-floor finding, where 182 stacks really do report exactly 2 series; that reasoning is sound for
# `grafanacloud_instance_active_otlp_series` and does not transfer to these fields.
#
# It is deliberately NOT imported here, so a future edit cannot reach for it by reflex.
# `> 0` is used instead, and it is CALIBRATED rather than assumed. Against the `grafanacloud-usage`
# datasource over 24h - an independent measurement sharing no code with this pillar - `> 0` on the
# inventory field reproduces it almost exactly:
#
# signal this pillar (> 0) usage datasource (24h)
# metrics 231 231
# traces 230 230
# profiles 0 0
# logs 249 269
#
# Three of four match to the stack, and logs is 20 low because an inventory snapshot lags a 24h window.
# **If a future change makes these diverge, the inventory field is the one to distrust** - the usage
# datasource is the billing system's own view.
ADOPTION_FLOOR = 0

# Dimensions benchmarked as median / p90 / worst. Names are bounded and fixed.
BENCHMARKS = (
    "active_series",
    "series_per_billed_user",
    "dashboards_per_user",
    "stickiness",
    "alert_rules",
    "admin_share",
    "datasource_types",
    "signals_in_use",
    "maturity_score",
    "adaptive_adoption",
)

# No currency without a rate card, and the reason stated rather than a blank panel. Deliberately
# carries no measured figure: those go stale in always-on prose and this text is always on screen.
SAVINGS_NO_RATECARD_NOTE = (
    "VOLUME, not currency, because this deployment has no rate card. The series reduction below is "
    "real and measured: it is the sum of positive marginal reductions for Adaptive Metrics `add` and "
    "`update` actions; `keep` and `remove` are not new savings. To see it as money, upload your "
    "contracted rates to `config/ratecard.csv` in the deployment bucket - see "
    "docs/ratecard.example.csv. Rates are never inferred."
)
SAVINGS_NO_METRICS_RATE_NOTE = (
    "VOLUME, not currency, because the supplied rate card does not price `metrics_series`. The series "
    "reduction below is real and measured, but pricing another dimension cannot be substituted or "
    "presented as a partial total. Add the contracted metrics-series rate to `config/ratecard.csv`."
)
SAVINGS_DPM_PANEL_NOTE = (
    "VOLUME here; the supplied `metrics_series` rate is DPM-aware, so currency requires each stack's "
    "30-day p95 active-series and total-DPM inputs from `grafanacloud-usage`. Those inputs stay in a "
    "live panel with zero pipeline series. This collector view therefore emits no currency value; "
    "absence is not zero saving."
)


def _percentiles(values: list[float]) -> dict[str, float | None]:
    """Median / p90 / worst. Never a mean - one extreme stack can define it."""
    clean = sorted(v for v in values if v is not None)
    if not clean:
        return {"median": None, "p90": None, "worst": None}
    at = lambda p: clean[min(len(clean) - 1, int(p * len(clean)))]
    return {"median": at(0.5), "p90": at(0.9), "worst": clean[-1]}


def build(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    dataplane: dict[str, Any] | None = None,
    ratecard: "RateCard | None" = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    dataplane = dataplane or {}
    metrics: list[tuple[str, dict[str, str], float]] = []

    total_series = sum(s.get("hmInstancePromCurrentActiveSeries") or 0 for s in stacks)
    billed = sum(s.get("billingActiveUsers") or 0 for s in stacks)
    active = sum(s.get("currentActiveUsers") or 0 for s in stacks)

    # Unit economics. Series per BILLED user; the active count is a 17% error here.
    metrics.append((
        "gcinsight_value_unit_cost_per_billed_user", {},
        round(total_series / billed, 1) if billed else 0.0,
    ))

    for signal, field in SIGNAL_FIELDS.items():
        adopters = len([s for s in stacks if (s.get(field) or 0) > ADOPTION_FLOOR])
        metrics.append((
            "gcinsight_value_adoption_ratio", {"signal": signal},
            round(100 * adopters / len(stacks), 2) if stacks else 0.0,
        ))

    # --- Benchmarks. Values per stack, then median/p90/worst. ---
    scored = {str(s["slug"]): score_stack(s, dataplane.get(str(s["slug"])))
              for s in stacks}

    def _per_stack(key: str) -> list[float]:
        out: list[float] = []
        for s in stacks:
            slug = str(s["slug"])
            users = s.get("currentActiveUsers") or 0
            b = s.get("billingActiveUsers") or 0
            am = (dataplane.get(slug) or {}).get("adaptive_metrics") or {}
            value: float | None
            if key == "active_series":
                value = float(s.get("hmInstancePromCurrentActiveSeries") or 0)
            elif key == "series_per_billed_user":
                value = (s.get("hmInstancePromCurrentActiveSeries") or 0) / b if b else None
            elif key == "dashboards_per_user":
                value = (s.get("dashboardCnt") or 0) / users if users else None
            elif key == "stickiness":
                value = (s.get("dailyUserCnt") or 0) / users if users else None
            elif key == "alert_rules":
                value = float(s.get("alertCnt") or 0)
            elif key == "admin_share":
                value = 100 * (s.get("currentActiveAdminUsers") or 0) / users if users else None
            elif key == "datasource_types":
                value = float(len([1 for v in (s.get("datasourceCnts") or {}).values() if v]))
            elif key == "signals_in_use":
                # Same unit trap as the adoption ratio: with the series floor this counted only the
                # metrics field, so every stack shipping logs and traces scored 1 signal in use.
                value = float(len([1 for f in SIGNAL_FIELDS.values()
                                   if (s.get(f) or 0) > ADOPTION_FLOOR]))
            elif key == "maturity_score":
                value = scored[slug]["score"]
            elif key == "adaptive_adoption":
                total = (am.get("rules_applied") or 0) + (am.get("recommendations_pending") or 0)
                value = 100 * (am.get("rules_applied") or 0) / total if total else None
            else:
                value = None
            if value is not None:
                out.append(round(float(value), 3))
        return out

    benchmark_rows: list[dict[str, Any]] = []
    for key in BENCHMARKS:
        values = _per_stack(key)
        p = _percentiles(values)
        benchmark_rows.append({
            " Dimension": key,
            "Stacks with data": len(values),
            "Median": p["median"],
            "p90": p["p90"],
            "Worst": p["worst"],
        })
        if p["median"] is not None:
            metrics.append(("gcinsight_value_benchmark", {"kind": key}, float(p["median"])))

    # --- Remediable series, measured per metric rather than estimated per stack. ---
    #
    # This used to sum the WHOLE active-series count of every stack that had not adopted Adaptive,
    # which claims the entire stack is remediable and overstates the saving by a wide margin. The real
    # figure is the sum of positive marginal reductions declared by savings-bearing add/update actions.
    #
    # `unused` is the subset whose metrics appear in no rule, query or dashboard in the API's observation
    # window. It is the lower-risk review queue, never permission to apply automatically: dependencies can
    # live outside Grafana or outside that window.
    adaptive_stacks_in_scope = [
        s for s in stacks
        if s.get("status") != "paused" and s.get("hmInstancePromUrl")
    ]
    adaptive = [
        (dataplane.get(str(s["slug"])) or {}).get("adaptive_metrics") or {}
        for s in adaptive_stacks_in_scope
    ]
    available_adaptive = [am for am in adaptive if am.get("available")]
    unadopted_stacks = [
        s for s in adaptive_stacks_in_scope
        if (am := (dataplane.get(str(s["slug"])) or {}).get("adaptive_metrics") or {}).get("available")
        and not am.get("adopted") and (am.get("recommendations_pending") or 0)
    ]
    remediable_series = sum(am.get("remediable_series") or 0 for am in available_adaptive)
    remediable_unused = sum(am.get("remediable_series_unused") or 0 for am in available_adaptive)
    recommendation_records = sum(am.get("recommendation_records_total") or 0
                                 for am in available_adaptive)
    recommendation_savings_records = sum(
        am.get("recommendation_records_savings_bearing",
               am.get("recommendation_records_total") or 0)
        for am in available_adaptive
    )
    recommendation_records_with_counts = sum(
        am.get("recommendation_records_with_series_counts") or 0 for am in available_adaptive
    )
    recommendation_records_missing_counts = sum(
        am.get("recommendation_records_missing_series_counts") or 0 for am in available_adaptive
    )
    complete_stacks = [am for am in available_adaptive if am.get("series_counts_complete") is True]
    # Estate savings are additive, so partial coverage cannot produce an honest estate total. One
    # non-verbose record or one failed recommendations request makes the volume unknown; it must not
    # oscillate between a partial number and the full number as endpoints recover.
    savings_complete = (
        bool(adaptive_stacks_in_scope)
        and len(adaptive) == len(adaptive_stacks_in_scope)
        and all(am.get("available") and am.get("series_counts_complete") is True for am in adaptive)
    )
    if dataplane and savings_complete:
        metrics.append(("gcinsight_value_savings_identified_series", {},
                        float(remediable_series)))
        metrics.append(("gcinsight_value_savings_unused_series", {},
                        float(remediable_unused)))
        if ratecard is not None:
            priced = ratecard.savings("metrics_series", total_series, remediable_series)
            priced_unused = ratecard.savings("metrics_series", total_series, remediable_unused)
            if priced is not None:
                metrics.append(("gcinsight_value_savings_identified_currency", {},
                                round(priced, 2)))
            if priced_unused is not None:
                metrics.append(("gcinsight_value_savings_unused_currency", {},
                                round(priced_unused, 2)))

    ranked = [e for e in scored.values() if e["score"] is not None]
    views: dict[str, list[dict[str, Any]]] = {
        "value_benchmarks": benchmark_rows,
        "value_summary": [{
            " Metric": "Stacks in scope",
            "Value": f"{len(stacks)} total, {coverage.scannable} scannable, {len(ranked)} maturity-ranked",
        }, {
            " Metric": "Billed users (the only figure valid for money)",
            "Value": billed,
        }, {
            " Metric": "Active users (adoption, NOT money)",
            "Value": active,
        }, {
            " Metric": "Active series org-wide",
            "Value": total_series,
        }, {
            " Metric": "Series per billed user",
            "Value": round(total_series / billed, 1) if billed else None,
        }, {
            " Metric": "Median maturity score",
            "Value": _percentiles([e["score"] for e in ranked])["median"],
        }, {
            " Metric": "Rubric version",
            "Value": RUBRIC_VERSION,
        }],
        "value_adoption": [
            {
                " Signal": signal,
                "Stacks using": len([s for s in stacks if (s.get(field) or 0) > ADOPTION_FLOOR]),
                "Share of estate %": round(
                    100 * len([s for s in stacks if (s.get(field) or 0) > ADOPTION_FLOOR]) / len(stacks), 1
                ) if stacks else None,
            }
            for signal, field in SIGNAL_FIELDS.items()
        ],
    }
    # Emit only with the data plane: a T1 run would otherwise overwrite the savings table with rows
    # reading "needs a T3 scan", which is worse than the real thing being a week old.
    if dataplane:
        priced_total = (ratecard.savings("metrics_series", total_series, remediable_series)
                        if ratecard is not None and savings_complete else None)
        priced_unused = (ratecard.savings("metrics_series", total_series, remediable_unused)
                         if ratecard is not None and savings_complete else None)
        pricing_scope = (ratecard.pricing_scope("metrics_series")
                         if ratecard is not None else None)
        metrics_rate = (ratecard.rates.get("metrics_series")
                        if ratecard is not None else None)
        currency_gap_note = (
            SAVINGS_NO_RATECARD_NOTE if ratecard is None
            else SAVINGS_DPM_PANEL_NOTE
            if metrics_rate is not None and metrics_rate.billing_basis == "dpm_aware"
            else SAVINGS_NO_METRICS_RATE_NOTE
        )
        rows = [{
            " Metric": "Stacks with pending recommendations and zero rules applied",
            "Value": len(unadopted_stacks),
        }, {
            " Metric": "Stacks with complete recommendation series counts",
            "Value": f"{len(complete_stacks)} of {len(adaptive_stacks_in_scope)} in scope",
        }, {
            " Metric": "Savings-bearing add/update records with marginal series counts",
            "Value": f"{recommendation_records_with_counts} of {recommendation_savings_records}",
        }, {
            " Metric": "Savings-bearing add/update records missing marginal series counts",
            "Value": recommendation_records_missing_counts,
        }, {
            " Metric": "All recommendation records (including keep/remove)",
            "Value": recommendation_records,
        }]
        if savings_complete:
            rows[:0] = [{
                " Metric": f"Savings from Adaptive Metrics, applying every recommendation "
                           f"({pricing_scope})"
                           if priced_total is not None else "Savings basis (series volume)",
                "Value": round(priced_total, 2) if priced_total is not None
                         else currency_gap_note,
            }, {
                " Metric": f"Of that base-rate saving, observed unused in the API window "
                           f"({pricing_scope})"
                           if priced_unused is not None
                           else "Review-free subset basis (series volume)",
                "Value": round(priced_unused, 2) if priced_unused is not None
                         else "same gap as the row above",
            }, {
                " Metric": "Remediable series, applying every recommendation",
                "Value": remediable_series,
            }, {
                " Metric": "Remediable series observed unused in the API window",
                "Value": remediable_unused,
            }, {
                " Metric": "Share of org active series that is remediable %",
                "Value": round(100 * remediable_series / total_series, 1) if total_series else None,
            }]
        views["value_savings"] = rows
    return metrics, views
