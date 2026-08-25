"""Pillar K: the affirmative observed-estate register and coverage depth.

Names stay in S3 views. Mimir receives only estate counts, per-stack counts, and enums bounded by the
versioned technology registry or the four signal types. Every row is driven by live inventory and a
successful atomic signal read; a failed stack is absent rather than represented by zeros.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from collector import observability_score, technology_registry

Metrics = list[tuple[str, dict[str, str], float]]
Views = dict[str, list[dict[str, Any]]]

MAX_SERVICES = 100
SERVICE_VIEW = "coverage_service_register"
TECHNOLOGY_VIEW = "coverage_technology_register"
METRIC_VIEW = "coverage_metric_name_register"
CLUSTER_VIEW = "coverage_cluster_register"
LEGACY_SERVICE_VIEW = "coverage_legacy_service_register"
SUMMARY_VIEW = "coverage_summary"

EPHEMERAL_IDENTITY = re.compile(
    r"(?:\.(?:scope|service|slice|socket|mount|timer|target|device)$|"
    r"^session-\d+|^user-\d+|\d{8,}|[0-9a-f]{8}-[0-9a-f]{4}-)"
)
UNSCORED_PAIRS = (
    ("profiles", "signal_not_in_use"),
    ("slo", "product_not_in_use"),
    ("alert", "product_not_in_use"),
    ("alert", "inventory_unavailable"),
    ("dashboard", "inventory_unavailable"),
    ("dashboard", "evidence_unavailable"),
    ("row", "ephemeral_identity"),
)

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    SERVICE_VIEW: (
        (" Stack", "string"), ("Service", "string"),
        ("Observability completeness %", "number"), ("Signals present", "number"),
        ("Metrics", "string"), ("Logs", "string"), ("Traces", "string"),
        ("Profiles", "string"), ("Has dashboard", "string"), ("Has alert", "string"),
        ("Has SLO", "string"), ("Has routed active alert", "string"),
        ("Applicable components", "number"), ("Unscored reason", "string"),
        ("Score numerator", "number"), ("Score maximum", "number"),
        ("Score version", "string"),
        ("Last seen", "time"),
    ),
    TECHNOLOGY_VIEW: (
        (" Stack", "string"), ("Technology", "string"), ("Technology key", "string"),
        ("Matched metric names", "number"), ("Registry version", "string"),
        ("Last seen", "time"),
    ),
    METRIC_VIEW: (
        (" Stack", "string"), ("Metric name", "string"), ("Technology", "string"),
        ("Registry version", "string"), ("Last seen", "time"),
    ),
    CLUSTER_VIEW: (
        (" Stack", "string"), ("Cluster", "string"), ("Last seen", "time"),
    ),
    LEGACY_SERVICE_VIEW: (
        (" Stack", "string"), ("Legacy service", "string"), ("Also canonical", "string"),
        ("Last seen", "time"),
    ),
    SUMMARY_VIEW: (
        (" Stack", "string"), ("Services discovered", "number"),
        ("Services retained", "number"), ("Technologies", "number"),
        ("Clusters", "number"), ("Metric names", "number"),
        ("Unmatched metric names", "number"),
        ("Legacy-only services", "number"), ("Legacy-only service share %", "number"),
        ("Registry version", "string"), ("Last seen", "time"),
    ),
}


def _normalise(value: Any) -> str:
    return value.strip().casefold() if isinstance(value, str) else ""


def _names(record: Mapping[str, Any], field: str) -> set[str]:
    raw = record.get(field)
    if not isinstance(raw, list):
        return set()
    return {name for value in raw if (name := _normalise(value))}


def _dashboard_services(record: Mapping[str, Any]) -> set[str]:
    if not record.get("available"):
        return set()
    services: set[str] = set()
    for dashboard in record.get("dashboards") or []:
        if not isinstance(dashboard, Mapping):
            continue
        for tag in dashboard.get("service_tags") or []:
            if not isinstance(tag, str) or not tag.casefold().startswith("service:"):
                continue
            if service := _normalise(tag.split(":", 1)[1]):
                services.add(service)
    return services


def _alert_services(record: Mapping[str, Any]) -> tuple[set[str], set[str]]:
    if not record.get("available"):
        return set(), set()
    alerts: set[str] = set()
    routed: set[str] = set()
    for route in record.get("service_routes") or []:
        if not isinstance(route, Mapping) or route.get("identity_label") != "service_name":
            continue
        service = _normalise(route.get("service_name"))
        if not service:
            continue
        alerts.add(service)
        if (
            not route.get("paused")
            and route.get("routing") == "direct"
            and route.get("receiver_state") == "provisioned"
        ):
            routed.add(service)
    return alerts, routed


def _component_state(value: bool | None, reason: str | None) -> str:
    if reason:
        return f"unscored: {reason}"
    return "yes" if value else "no"


def _slo_product_in_use(record: Mapping[str, Any], slos: set[str]) -> bool:
    """Use the same explicitly-windowed metric inventory that agreed with the SLO API census."""
    return bool(slos) or any(
        isinstance(name, str) and name.casefold().startswith("grafana_slo_")
        for name in record.get("metric_names") or []
    )


def _ephemeral(service: str) -> bool:
    return EPHEMERAL_IDENTITY.search(service) is not None


def _technology_count_bucket(count: int) -> str:
    if count <= 1:
        return str(count)
    if count <= 4:
        return "2-4"
    return "5+"


def build(
    stacks: Sequence[Mapping[str, Any]],
    signal_inventory: Mapping[str, Mapping[str, Any]] | None,
    *,
    dashboard_inventory: Mapping[str, Mapping[str, Any]] | None = None,
    alert_routing: Mapping[str, Mapping[str, Any]] | None = None,
    score_weights: Mapping[str, float] | None = None,
) -> tuple[Metrics, Views]:
    if signal_inventory is None:
        return [], {}

    weights = dict(score_weights or observability_score.parse_weights(""))
    metrics: Metrics = []
    service_rows: list[dict[str, Any]] = []
    technology_rows: list[dict[str, Any]] = []
    metric_rows: list[dict[str, Any]] = []
    cluster_rows: list[dict[str, Any]] = []
    legacy_rows: list[dict[str, Any]] = []
    summary_rows: list[dict[str, Any]] = []
    depth_counts = {depth: 0 for depth in range(1, 5)}
    signal_counts = {signal: 0 for signal in ("metrics", "logs", "traces", "profiles")}
    technology_stacks = {entry.key: 0 for entry in technology_registry.REGISTRY.entries}
    technology_count_distribution = {kind: 0 for kind in ("0", "1", "2-4", "5+")}
    classified_counts = {"matched": 0, "unmatched": 0}
    identity_counts = {"canonical": 0, "legacy_only": 0, "overlap": 0}
    unscored_counts: Counter[tuple[str, str]] = Counter()
    scored_percentages: list[float] = []
    scored_denominators: list[int] = []
    measured = 0

    for stack in stacks:
        slug = str(stack.get("slug") or "")
        record = signal_inventory.get(slug) or {}
        if not slug or not record.get("available"):
            continue
        measured += 1
        last_seen = str(record.get("window_end") or "")
        by_signal = {
            "metrics": _names(record, "metric_services"),
            "logs": _names(record, "log_services"),
            "traces": _names(record, "trace_services"),
            "profiles": _names(record, "profile_services"),
        }
        canonical = set().union(*by_signal.values())
        legacy = _names(record, "legacy_metric_services")
        slos = _names(record, "slo_services")
        legacy_only = legacy - canonical
        identity_counts["canonical"] += len(canonical)
        identity_counts["legacy_only"] += len(legacy_only)
        identity_counts["overlap"] += len(legacy & canonical)

        dashboard_record = (dashboard_inventory or {}).get(slug) or {}
        alert_record = (alert_routing or {}).get(slug) or {}
        dashboards = _dashboard_services(dashboard_record)
        alerts, routed = _alert_services(alert_record)
        profiles_in_use = bool(by_signal["profiles"])
        slo_in_use = _slo_product_in_use(record, slos)
        alert_available = bool(alert_record.get("available"))
        rules_total = alert_record.get("rules_total")
        alert_in_use = (
            alert_available and isinstance(rules_total, int)
            and not isinstance(rules_total, bool) and rules_total > 0
        )
        dashboard_available = bool(dashboard_record.get("available"))
        dashboard_evidence_available = dashboard_record.get("detail_available") is not False
        eligible_services = {service for service in canonical if not _ephemeral(service)}
        for signal, names in by_signal.items():
            signal_counts[signal] += len(names & eligible_services)
        rows = []
        for service in canonical:
            signals = [signal for signal, names in by_signal.items() if service in names]
            depth = len(signals)
            row_unscored = "ephemeral_identity" if _ephemeral(service) else None
            if row_unscored is None:
                depth_counts[depth] += 1
            components: dict[str, bool | None] = {
                "metrics": service in by_signal["metrics"],
                "logs": service in by_signal["logs"],
                "traces": service in by_signal["traces"],
                "profiles": service in by_signal["profiles"] if profiles_in_use else None,
                "dashboard": (
                    service in dashboards
                    if dashboard_available and dashboard_evidence_available else None
                ),
                "alert": service in alerts if alert_in_use else None,
                "slo": service in slos if slo_in_use else None,
            }
            reasons: dict[str, str] = {}
            if not profiles_in_use:
                reasons["profiles"] = "signal_not_in_use"
            if not slo_in_use:
                reasons["slo"] = "product_not_in_use"
            if not alert_available:
                reasons["alert"] = "inventory_unavailable"
            elif not alert_in_use:
                reasons["alert"] = "product_not_in_use"
            if not dashboard_available:
                reasons["dashboard"] = "inventory_unavailable"
            elif not dashboard_evidence_available:
                reasons["dashboard"] = "evidence_unavailable"
            applicable_count = sum(isinstance(value, bool) for value in components.values())
            score = observability_score.calculate(components, weights)
            if score is None:
                continue
            numerator, maximum, percentage = score
            if row_unscored:
                unscored_counts[("row", row_unscored)] += 1
                percentage = None
            else:
                for component, reason in reasons.items():
                    unscored_counts[(component, reason)] += 1
                if percentage is not None:
                    scored_percentages.append(percentage)
                    scored_denominators.append(applicable_count)
            rows.append({
                " Stack": slug,
                "Service": service,
                "Observability completeness %": percentage,
                "Signals present": depth,
                "Metrics": "yes" if components["metrics"] else "no",
                "Logs": "yes" if components["logs"] else "no",
                "Traces": "yes" if components["traces"] else "no",
                "Profiles": _component_state(components["profiles"], reasons.get("profiles")),
                "Has dashboard": _component_state(
                    components["dashboard"], reasons.get("dashboard")
                ),
                "Has alert": _component_state(components["alert"], reasons.get("alert")),
                "Has SLO": _component_state(components["slo"], reasons.get("slo")),
                "Has routed active alert": "yes" if service in routed else "no",
                "Applicable components": applicable_count,
                "Unscored reason": row_unscored or "",
                "Score numerator": numerator,
                "Score maximum": maximum,
                "Score version": observability_score.VERSION,
                "Last seen": last_seen,
            })
        rows.sort(key=lambda row: (
            row["Observability completeness %"] is None,
            -(row["Observability completeness %"] or 0), row["Service"],
        ))
        service_rows.extend(rows[:MAX_SERVICES])

        classification = technology_registry.classify(record.get("metric_names") or [])
        technology_count_distribution[
            _technology_count_bucket(len(classification["technologies"]))
        ] += 1
        tech_by_metric: dict[str, str] = {}
        for technology in classification["technologies"]:
            technology_stacks[technology["key"]] += 1
            for metric_name in technology["matched_metric_names"]:
                tech_by_metric[metric_name] = technology["name"]
            technology_rows.append({
                " Stack": slug,
                "Technology": technology["name"],
                "Technology key": technology["key"],
                "Matched metric names": technology["matched_metric_name_count"],
                "Registry version": classification["registry_version"],
                "Last seen": last_seen,
            })
        classified_counts["matched"] += classification["matched_metric_name_count"]
        classified_counts["unmatched"] += classification["unmatched_metric_name_count"]
        for metric_name in sorted(record.get("metric_names") or []):
            metric_rows.append({
                " Stack": slug,
                "Metric name": metric_name,
                "Technology": tech_by_metric.get(metric_name, "(unmatched)"),
                "Registry version": classification["registry_version"],
                "Last seen": last_seen,
            })

        clusters = sorted(_names(record, "clusters"))
        cluster_rows.extend({" Stack": slug, "Cluster": name, "Last seen": last_seen}
                            for name in clusters)
        legacy_rows.extend({
            " Stack": slug,
            "Legacy service": service,
            "Also canonical": "yes" if service in canonical else "no",
            "Last seen": last_seen,
        } for service in sorted(legacy))

        legacy_denominator = len(canonical) + len(legacy_only)
        summary_rows.append({
            " Stack": slug,
            "Services discovered": len(canonical),
            "Services retained": min(len(canonical), MAX_SERVICES),
            "Technologies": len(classification["technologies"]),
            "Clusters": len(clusters),
            "Metric names": classification["total_metric_name_count"],
            "Unmatched metric names": classification["unmatched_metric_name_count"],
            "Legacy-only services": len(legacy_only),
            "Legacy-only service share %": (
                None if not legacy_denominator else round(len(legacy_only) / legacy_denominator * 100, 1)
            ),
            "Registry version": classification["registry_version"],
            "Last seen": last_seen,
        })
        metrics.extend([
            ("gcinsight_coverage_stack_services", {"stack": slug}, float(len(eligible_services))),
            ("gcinsight_coverage_stack_technologies", {"stack": slug},
             float(len(classification["technologies"]))),
            ("gcinsight_coverage_stack_clusters", {"stack": slug}, float(len(clusters))),
        ])

    metrics.append(("gcinsight_coverage_stacks_measured", {}, float(measured)))
    metrics.extend(
        ("gcinsight_coverage_services_by_depth", {"kind": str(depth)}, float(count))
        for depth, count in depth_counts.items()
    )
    metrics.extend(
        ("gcinsight_coverage_services_by_signal", {"kind": signal}, float(count))
        for signal, count in signal_counts.items()
    )
    metrics.extend(
        ("gcinsight_coverage_technology_stacks", {"kind": entry.key},
         float(technology_stacks[entry.key]))
        for entry in technology_registry.REGISTRY.entries
    )
    metrics.extend(
        ("gcinsight_coverage_stacks_by_technology_count", {"kind": kind}, float(count))
        for kind, count in technology_count_distribution.items()
    )
    metrics.extend(
        ("gcinsight_coverage_metric_names", {"kind": kind}, float(value))
        for kind, value in classified_counts.items()
    )
    metrics.extend(
        ("gcinsight_coverage_service_identity", {"kind": kind}, float(value))
        for kind, value in identity_counts.items()
    )
    metrics.extend(
        ("gcinsight_coverage_unscored", {"component": component, "reason": reason},
         float(unscored_counts[(component, reason)]))
        for component, reason in UNSCORED_PAIRS
    )
    if scored_percentages:
        metrics.extend([
            ("gcinsight_coverage_service_completeness_mean",
             {"version": observability_score.VERSION},
             round(sum(scored_percentages) / len(scored_percentages), 1)),
            ("gcinsight_coverage_service_applicable_components_mean",
             {"version": observability_score.VERSION},
             round(sum(scored_denominators) / len(scored_denominators), 2)),
        ])
    return metrics, {
        SERVICE_VIEW: service_rows,
        TECHNOLOGY_VIEW: sorted(technology_rows, key=lambda row: (row["Technology"], row[" Stack"])),
        METRIC_VIEW: metric_rows,
        CLUSTER_VIEW: cluster_rows,
        LEGACY_SERVICE_VIEW: legacy_rows,
        SUMMARY_VIEW: summary_rows,
    }
