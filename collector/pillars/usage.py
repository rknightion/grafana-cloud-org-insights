"""Pillar C - what stack consumers actually do with Grafana Cloud (PLAN 4.3).

This is the inventory half of Pillar C: everything below comes from the T1 inventory, plus optional
T2 per-stack user detail. The richer per-dashboard, per-panel and viewer analytics and query-cost
attribution are live in Pillar J. It queries each stack's own usage-insights datasource with that
stack's read-only reader and publishes its measured coverage on the Dashboard usage dashboard.

Two traps this module exists to avoid:

- **`grafana-knowledgegraph-datasource` is auto-provisioned estate-wide.** Counted, it becomes the
  most-adopted plugin and means nothing. `EXCLUDED_DATASOURCES` drops it.
- **A two-series synthetic floor exists across much of the estate**, so thresholding signal adoption at
  `> 0` reports near-universal adoption. The deliberately conservative floor is `USAGE_FLOOR` (1000),
  shared with Pillar B. The dated distribution and sensitivity check are committed in
  `evidence/otlp-floor.json`; re-measure them before quoting adoption counts.

Stickiness is `dailyUserCnt / currentActiveUsers`. It is deliberately not a money figure, so it uses the
*active* count, not the billed one: the question is "of the people who have access, how many showed up
today", which `billingActiveUsers` would answer wrongly.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from collector.coverage import Coverage
from collector.pillars.cost import USAGE_FLOOR

# Auto-provisioned by Grafana on every stack. Counting it makes it the estate's top plugin.
EXCLUDED_DATASOURCES = frozenset({"grafana-knowledgegraph-datasource"})

# Signal presence, for "which products is this stack actually using".
SIGNAL_FIELDS = {
    "metrics": "hmInstancePromCurrentUsage",
    "logs": "hlInstanceCurrentUsage",
    "traces": "htInstanceCurrentUsage",
    "profiles": "hpInstanceCurrentUsage",
    "graphite": "hmInstanceGraphiteCurrentUsage",
}

# Buckets for user recency. `never` is its own bucket because it is the actionable one.
LAST_SEEN_BUCKETS = ("7d", "30d", "90d", "older", "never")

# `usage_dormant_stacks` is a condition-matched finding list, so empty is a healthy, legitimate state.
# Infinity still needs an explicit schema in that state or the dashboard build fails.
ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"),
    ("Region", "string"),
    ("Users (active)", "number"),
    ("Users (daily)", "number"),
    ("Stickiness", "number"),
    ("Admins", "number"),
    ("Editors", "number"),
    ("Viewers", "number"),
    ("Dashboards", "number"),
    ("Alert rules", "number"),
    ("Datasource types", "number"),
    ("Signals in use", "number"),
    ("Signals", "string"),
    ("Age (days)", "number"),
)

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "usage_dormant_stacks": ROW_SCHEMA,
}


def _age_days(iso: str | None, now: dt.datetime) -> float | None:
    if not iso:
        return None
    try:
        then = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return (now - then).total_seconds() / 86400


def _bucket(days: float | None) -> str:
    if days is None:
        return "never"
    if days <= 7:
        return "7d"
    if days <= 30:
        return "30d"
    if days <= 90:
        return "90d"
    return "older"


def _signals_in_use(stack: dict[str, Any]) -> list[str]:
    return [sig for sig, field in SIGNAL_FIELDS.items() if (stack.get(field) or 0) > USAGE_FLOOR]


def build(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    stack_detail: dict[str, Any] | None = None,
    now: dt.datetime | None = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    """`stack_detail` is the optional T2 payload; without it the user-recency half is skipped."""
    now = now or dt.datetime.now(dt.timezone.utc)
    stack_detail = stack_detail or {}
    metrics: list[tuple[str, dict[str, str], float]] = []
    rows: list[dict[str, Any]] = []

    for s in stacks:
        slug = str(s["slug"])
        active = s.get("currentActiveUsers") or 0
        daily = s.get("dailyUserCnt") or 0
        datasources = {k: v for k, v in (s.get("datasourceCnts") or {}).items()
                       if v and k not in EXCLUDED_DATASOURCES}
        signals = _signals_in_use(s)
        rows.append({
            " Stack": slug,
            "Region": s.get("regionSlug"),
            "Users (active)": active,
            "Users (daily)": daily,
            # Of the people with access, how many showed up today.
            "Stickiness": round(daily / active, 3) if active else None,
            "Admins": s.get("currentActiveAdminUsers") or 0,
            "Editors": s.get("currentActiveEditorUsers") or 0,
            "Viewers": s.get("currentActiveViewerUsers") or 0,
            "Dashboards": s.get("dashboardCnt") or 0,
            "Alert rules": s.get("alertCnt") or 0,
            "Datasource types": len(datasources),
            "Signals in use": len(signals),
            # Unbounded strings, so view-only.
            "Signals": ", ".join(signals) or None,
            "Age (days)": round(a, 1) if (a := _age_days(s.get("createdAt"), now)) is not None else None,
        })

    active_total = sum(s.get("currentActiveUsers") or 0 for s in stacks)
    daily_total = sum(s.get("dailyUserCnt") or 0 for s in stacks)
    metrics.append((
        "gcinsight_usage_stickiness_ratio", {},
        round(daily_total / active_total, 4) if active_total else 0.0,
    ))

    # Plugin adoption = stacks with at least one instance, not instance count. One stack with 12
    # Infinity datasources is not 12 stacks' worth of adoption.
    adoption: dict[str, int] = {}
    instances: dict[str, int] = {}
    for s in stacks:
        for name, count in (s.get("datasourceCnts") or {}).items():
            if not count or name in EXCLUDED_DATASOURCES:
                continue
            adoption[name] = adoption.get(name, 0) + 1
            instances[name] = instances.get(name, 0) + count
    for name, count in sorted(adoption.items()):
        metrics.append(("gcinsight_usage_plugin_adoption", {"kind": name}, float(count)))

    for signal in SIGNAL_FIELDS:
        metrics.append((
            "gcinsight_usage_stacks_by_signal", {"signal": signal},
            float(len([s for s in stacks if signal in _signals_in_use(s)])),
        ))

    # --- User recency, T2 only. ---
    buckets = {b: 0 for b in LAST_SEEN_BUCKETS}
    user_rows: list[dict[str, Any]] = []
    for slug, detail in stack_detail.items():
        for user in (detail or {}).get("users", []) or []:
            days = _age_days(user.get("lastSeenAt"), now)
            display_days = round(days, 1) if days is not None else None
            bucket = _bucket(display_days)
            buckets[bucket] += 1
            user_rows.append({
                " Stack": slug,
                # PII is in scope and stored in clear (CLAUDE.md). On the organisation stacks `login` IS the email.
                "User": user.get("login") or user.get("email"),
                "Name": user.get("name"),
                "Role": user.get("role"),
                "Last seen (days)": display_days,
                "Recency": bucket,
            })
    if stack_detail:
        for bucket, count in buckets.items():
            metrics.append((
                "gcinsight_usage_users_last_seen_bucket", {"kind": bucket}, float(count)
            ))

    views: dict[str, list[dict[str, Any]]] = {
        "usage": sorted(rows, key=lambda r: -(r["Users (active)"] or 0)),
        "usage_plugin_adoption": sorted(
            [
                {
                    " Plugin": name,
                    "Stacks": count,
                    "Share of estate %": round(100 * count / len(stacks), 1) if stacks else None,
                    "Total instances": instances[name],
                }
                for name, count in adoption.items()
            ],
            key=lambda r: -r["Stacks"],
        ),
        # Provisioned, populated, and nobody logs in. The clearest "paid for, not used" list.
        "usage_dormant_stacks": sorted(
            [r for r in rows if r["Users (daily)"] == 0 and r["Users (active)"] > 0],
            key=lambda r: -(r["Dashboards"] or 0),
        ),
        "usage_summary": [{
            " Metric": "Stickiness (daily / active users, estate)",
            "Value": round(daily_total / active_total, 3) if active_total else None,
        }, {
            " Metric": "Active users",
            "Value": active_total,
        }, {
            " Metric": "Daily users",
            "Value": daily_total,
        }, {
            " Metric": "Datasource types in use (excl. auto-provisioned)",
            "Value": len(adoption),
        }, {
            " Metric": "Stacks with users but zero daily activity",
            "Value": len([r for r in rows if r["Users (daily)"] == 0 and r["Users (active)"] > 0]),
        }, {
            " Metric": "Per-dashboard and per-panel view analytics",
            "Value": "Live - see Dashboard usage; coverage is measured by the per-stack reader sweep.",
        }],
    }
    if stack_detail:
        views["usage_user_recency"] = sorted(
            user_rows, key=lambda r: (r["Last seen (days)"] is None, -(r["Last seen (days)"] or 0))
        )
        views["usage_summary"].insert(0, {
            " Metric": "Stacks with user detail",
            "Value": f"{len(stack_detail)} of {coverage.scannable} scannable",
        })
    return metrics, views
