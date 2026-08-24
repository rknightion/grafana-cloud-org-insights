"""Pillar B - cost, framed as diagnosis rather than as an invoice (PLAN 4.2, 0.5).

**Many orgs already run showback.** A per-owner monthly cost email telling each
stack owner what their stack cost. So a second "here is your number" table adds nothing, and this pillar
deliberately does not build one. It answers the two questions the email cannot: *why* is the number that
size, and *which lever moves it*.

Three levers, ordered by the volume they can actually remove in the current deployment:

1. **Adaptive Metrics headroom** - marginal series reductions from pending recommendations.
2. **Cardinality outliers** - stacks and labels whose cardinality is concentrated enough to act on.
3. **Efficiency ratio** - series per *billed* user, which normalises a big stack against a busy one.

Money rules, both learned the hard way:

- **`billingActiveUsers` is the only user count valid for money**, never `currentActiveUsers`.
- **`CurrentUsage` and `BillingUsage` are different questions.** Every figure here names which one it
  used; nothing averages them.

Currency is emitted only for dimensions present in the optional rate card. Adaptive Metrics savings use
the verbose response's marginal before-minus-after reduction; a missing rate or missing count remains
absent rather than becoming a zero or an inferred total.
"""

from __future__ import annotations

from typing import Any

from collector.coverage import Coverage

# Inventory field pairs per billable signal. Graphite is included because 2 stacks genuinely use it;
# it is absent from usage-insights `instance_type`, which is a different thing entirely.
SIGNAL_USAGE = {
    "metrics": ("hmInstancePromCurrentUsage", "hmInstancePromBillingUsage"),
    "logs": ("hlInstanceCurrentUsage", "hlInstanceBillingUsage"),
    "traces": ("htInstanceCurrentUsage", "htInstanceBillingUsage"),
    "profiles": ("hpInstanceCurrentUsage", "hpInstanceBillingUsage"),
    "graphite": ("hmInstanceGraphiteCurrentUsage", "hmInstanceGraphiteBillingUsage"),
}

# 182 stacks report exactly 2 OTLP series as a synthetic floor (measured, `testdata/otlp-floor.json`;
# NONE report 0, so ">0" is satisfied by every stack that reports at all), so ">0" would report near-universal
# adoption of everything. Anything at or below this is not real usage.
USAGE_FLOOR = 1000

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "cost_adaptive_metric_recommendations": (
        (" Stack", "string"), ("Metric", "string"), ("Current series", "number"),
        ("Recommended series", "number"), ("Removable series", "number"),
        ("Dependencies", "number"),
    ),
    "cost_adaptive_logs": (
        (" Stack", "string"), ("Recommendations", "number"), ("Pending", "number"),
        ("Applied", "number"), ("Pending GB", "number"),
        ("Pending GB (unqueried)", "number"), ("Levels", "string"),
    ),
}


def _num(stack: dict[str, Any], field: str) -> float:
    return float(stack.get(field) or 0)


def _adaptive(dataplane: dict[str, Any], slug: str) -> dict[str, Any] | None:
    entry = (dataplane or {}).get(slug) or {}
    am = entry.get("adaptive_metrics") or {}
    return am if am.get("available") else None


def _cardinality(dataplane: dict[str, Any], slug: str) -> dict[str, Any] | None:
    entry = (dataplane or {}).get(slug) or {}
    card = entry.get("cardinality") or {}
    return card if card.get("available") else None


def build(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    dataplane: dict[str, Any] | None = None,
    adaptive_logs: dict[str, Any] | None = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    """Inventory is required; `dataplane` (T3) and `adaptive_logs` (T2) each add an optional half."""
    dataplane = dataplane or {}
    adaptive_logs = adaptive_logs or {}
    rows: list[dict[str, Any]] = []
    metrics: list[tuple[str, dict[str, str], float]] = []

    for s in stacks:
        slug = str(s["slug"])
        series = _num(s, "hmInstancePromCurrentActiveSeries")
        billed = _num(s, "billingActiveUsers")
        am = _adaptive(dataplane, slug)
        card = _cardinality(dataplane, slug)

        rows.append({
            " Stack": slug,
            "Region": s.get("regionSlug"),
            "Active series": int(series),
            "Users (billed)": int(billed),
            # The efficiency ratio. A stack with 3M series and 17 users is a different problem from
            # one with 3M series and 400.
            "Series per billed user": round(series / billed, 1) if billed else None,
            "Adaptive rules applied": am["rules_applied"] if am else None,
            "Adaptive recs pending": am["recommendations_pending"] if am else None,
            "Adaptive adopted": am["adopted"] if am else None,
            "Label values": card["label_values_count_total"] if card else None,
            "Label names": card["label_names_count"] if card else None,
        })

        metrics.append(("gcinsight_stack_active_series", {"stack": slug}, series))
        metrics.append(("gcinsight_stack_billed_users", {"stack": slug}, billed))
        if am:
            metrics.append(("gcinsight_adaptive_recommendations", {"stack": slug, "status": "pending"},
                            float(am["recommendations_pending"])))
            metrics.append(("gcinsight_adaptive_recommendations", {"stack": slug, "status": "applied"},
                            float(am["rules_applied"])))

    # --- Estate rollups. `cost_billed_users` is Pillar A's; recomputing it here would duplicate a
    # --- series (guard.check_no_duplicates), so this pillar owns the ratio, not the total.
    total_series = sum(_num(s, "hmInstancePromCurrentActiveSeries") for s in stacks)
    total_billed = sum(_num(s, "billingActiveUsers") for s in stacks)
    metrics.append((
        "gcinsight_cost_series_per_billed_user", {},
        round(total_series / total_billed, 1) if total_billed else 0.0,
    ))

    for signal, (current_field, billing_field) in SIGNAL_USAGE.items():
        # `CurrentUsage`, named explicitly. The billing figure is a separate column in the view, never
        # merged with this one - they disagree by up to 31 stacks.
        metrics.append((
            "gcinsight_cost_usage_by_signal", {"signal": signal},
            sum(_num(s, current_field) for s in stacks),
        ))

    adaptive = [(_adaptive(dataplane, str(s["slug"])), s) for s in stacks]
    measured = [(am, s) for am, s in adaptive if am]
    unadopted = [(am, s) for am, s in measured if not am["adopted"] and am["recommendations_pending"]]

    # Emit ONLY if the data plane was actually measured. Without it these are both structurally 0, and a
    # 0 published at a later timestamp than the real T3 value overwrites it - so an hourly T1 would erase
    # the estate's single largest finding every hour. The carry-forward cannot save a series the live
    # tier claims to own (PLAN 5.3).
    if measured:
        metrics.append(("gcinsight_cost_adaptive_rules_applied_total", {},
                        float(sum(am["rules_applied"] for am, _ in measured))))
        metrics.append(("gcinsight_cost_stacks_without_adaptive", {}, float(len(unadopted))))

    # --- Adaptive LOGS. A separate input from a separate tier, so it gets its own guard: the same
    # "a gap is an absent series, never a zero" rule that stops an hourly T1 erasing T3's findings.
    #
    # **Only the PENDING saving is emitted, and there is deliberately no applied-saving metric here.**
    # The API reports a pattern's RESIDUAL volume, so one already dropped at a high rate reports almost
    # no bytes and `volume * configured/100` computes to nothing. The applied half is measured by
    # `grafanacloud_logs_instance_adaptivelogs_bytes_dropped_
    # per_second` on the usage datasource, which needs no credential and no series of ours. Panel, not
    # pipeline.
    logs_ok = [v for v in (adaptive_logs.get(str(s["slug"])) for s in stacks)
               if isinstance(v, dict) and v.get("available")]
    if logs_ok:
        with_recs = [v for v in logs_ok if v.get("recommendations")]
        metrics.append(("gcinsight_cost_adaptivelogs_stacks_measured", {}, float(len(logs_ok))))
        metrics.append(("gcinsight_cost_adaptivelogs_stacks_with_recommendations", {},
                        float(len(with_recs))))
        # The headline: stacks holding recommendations that have applied NONE of them.
        metrics.append(("gcinsight_cost_adaptivelogs_stacks_none_applied", {},
                        float(len([v for v in with_recs if not v.get("applied")]))))
        metrics.append(("gcinsight_cost_adaptivelogs_recommendations_total", {},
                        float(sum(v.get("recommendations") or 0 for v in logs_ok))))
        metrics.append(("gcinsight_cost_adaptivelogs_pending_total", {},
                        float(sum(v.get("pending") or 0 for v in logs_ok))))
        metrics.append(("gcinsight_cost_adaptivelogs_pending_bytes_total", {},
                        float(sum(v.get("pending_bytes") or 0 for v in logs_ok))))
        # The subset needing no review conversation, because nothing has queried those lines.
        metrics.append(("gcinsight_cost_adaptivelogs_pending_bytes_unqueried", {},
                        float(sum(v.get("pending_bytes_unqueried") or 0 for v in logs_ok))))
        for v in with_recs:
            metrics.append(("gcinsight_cost_adaptivelogs_pending_bytes",
                            {"stack": str(v["slug"])}, float(v.get("pending_bytes") or 0)))

    views: dict[str, list[dict[str, Any]]] = {
        "cost": sorted(rows, key=lambda r: -(r["Active series"] or 0)),
    }
    if logs_ok:
        # Only stacks that HAVE recommendations. Including every measured stack would make this the inventory again -
        # the same mistake `risk_service_accounts` and `cost_cardinality_outliers` had to be filtered
        # out of. `Applied` is a COUNT of patterns already dropped, never a saving: see the metric
        # block above for why the bytes cannot be recovered.
        views["cost_adaptive_logs"] = [
                {
                    " Stack": str(v["slug"]),
                    "Recommendations": v.get("recommendations"),
                    "Pending": v.get("pending"),
                    "Applied": v.get("applied"),
                    "Pending GB": round((v.get("pending_bytes") or 0) / 1024 ** 3, 6),
                    "Pending GB (unqueried)": round(
                        (v.get("pending_bytes_unqueried") or 0) / 1024 ** 3, 6),
                    "Levels": ", ".join(v.get("levels") or []) or None,
                }
                for v in sorted(
                    (record for record in logs_ok if record.get("recommendations")),
                    key=lambda record: -(record.get("pending_bytes") or 0),
                )
            ]
    # Emit ONLY with the data plane. Every tier writes every view it returns, so a T1 run would
    # overwrite T3's 106-row headroom table with an empty one and the panel would read "nothing to fix".
    if measured:
        # The bounded action list behind the estate saving. Each stack source retains at most ten
        # recommendations, so this is a review queue rather than an unbounded metric-name inventory.
        # Metric identity is deliberately a view field, never a Mimir label.
        views["cost_adaptive_metric_recommendations"] = sorted(
            [
                {
                    " Stack": str(s["slug"]),
                    "Metric": recommendation.get("metric"),
                    "Current series": recommendation.get("current_series"),
                    "Recommended series": recommendation.get("recommended_series"),
                    "Removable series": recommendation.get("remediable_series"),
                    "Dependencies": recommendation.get("used_in"),
                }
                for am, s in measured
                for recommendation in (am.get("sample_recommendations") or [])
            ],
            key=lambda row: (-(row["Removable series"] or 0), row[" Stack"], row["Metric"] or ""),
        )
        # Sorted by remediable volume, not by spend - the point is what to fix first.
        views["cost_adaptive_headroom"] = sorted(
            [
                {
                    " Stack": str(s["slug"]),
                    "Active series": int(_num(s, "hmInstancePromCurrentActiveSeries")),
                    "Recs pending": am["recommendations_pending"],
                    "Rules applied": am["rules_applied"],
                    "Share of org series %": round(
                        100 * _num(s, "hmInstancePromCurrentActiveSeries") / total_series, 2
                    ) if total_series else None,
                }
                for am, s in unadopted
            ],
            key=lambda r: -(r["Active series"] or 0),
        )
        views["cost_cardinality_outliers"] = sorted(
            [
                {
                    " Stack": str(s["slug"]),
                    "Label values": card["label_values_count_total"],
                    "Label names": card["label_names_count"],
                    "Active series": int(_num(s, "hmInstancePromCurrentActiveSeries")),
                    # Names are unbounded, so the worst offender rides in the view, never a label.
                    "Worst label": (card["top_labels"][0]["label"] if card.get("top_labels") else None),
                    "Worst label values": (card["top_labels"][0]["values"] if card.get("top_labels") else None),
                }
                for s in stacks
                for card in [_cardinality(dataplane, str(s["slug"]))]
                if card and card.get("label_values_count_total")
            ],
            key=lambda r: -(r["Label values"] or 0),
        )
    views["cost_signal_usage"] = [
            {
                " Signal": signal,
                "Current usage": sum(_num(s, cur) for s in stacks),
                "Billing usage": sum(_num(s, bill) for s in stacks),
                # Two different questions; the gap is the interesting column.
                "Stacks above floor (current)": len([s for s in stacks if _num(s, cur) > USAGE_FLOOR]),
                "Stacks above floor (billing)": len([s for s in stacks if _num(s, bill) > USAGE_FLOOR]),
            }
            for signal, (cur, bill) in SIGNAL_USAGE.items()
    ]
    views["cost_summary"] = [{
            # The denominator, first row, because every figure below it is measured over this many
            # stacks and not over 271. A partial T3 must not read as a small estate (SPEC §5.2).
            " Metric": "Stacks measured for Adaptive",
            "Value": f"{len(measured)} of {coverage.scannable} scannable ({coverage.total} total)",
        }, {
            " Metric": "Adaptive recommendations pending (measured stacks)",
            "Value": sum(am["recommendations_pending"] for am, _ in measured),
        }, {
            " Metric": "Adaptive rules applied",
            "Value": sum(am["rules_applied"] for am, _ in measured),
        }, {
            " Metric": "Stacks with recommendations and zero rules applied",
            "Value": len(unadopted),
        }, {
            " Metric": "Active series on those stacks",
            "Value": int(sum(_num(s, "hmInstancePromCurrentActiveSeries") for _, s in unadopted)),
        }, {
            " Metric": "Their share of org series %",
            "Value": round(
                100 * sum(_num(s, "hmInstancePromCurrentActiveSeries") for _, s in unadopted) / total_series, 1
            ) if total_series else None,
        }, {
            " Metric": "Series per billed user (estate)",
            "Value": round(total_series / total_billed, 1) if total_billed else None,
        }, {
            # Loud on purpose. A savings panel that renders blank reads as "no savings available".
            " Metric": "Savings in currency",
            "Value": "not available - needs per-recommendation series reduction and the contracted rate card "
                     "(SPEC §11.3). Volume is the honest unit until then.",
    }]
    return metrics, views
