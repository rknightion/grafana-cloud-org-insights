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
    "usage_plugin_adoption": (
        (" Plugin", "string"), ("Stacks", "number"),
        ("Share of estate %", "number"), ("Total instances", "number"),
        ("Enterprise (current catalogue)", "boolean"),
        ("Catalogue stacks measured", "number"),
        ("Inventory stacks measured", "number"), ("Estate stacks", "number"),
    ),
    "usage_datasource_inventory": (
        (" Stack", "string"), ("Datasource type", "string"),
        ("Provisioned instances", "number"),
        ("Enterprise (current catalogue)", "boolean"),
        ("Catalogue basis", "string"),
    ),
    "usage_enterprise_catalogue": (
        (" Plugin", "string"), ("Enterprise (current catalogue)", "boolean"),
        ("Stacks (measured)", "number"), ("Configured instances (measured)", "number"),
        ("Catalogue stacks measured", "number"),
        ("Inventory stacks measured", "number"), ("Estate stacks", "number"),
        ("Catalogue basis", "string"),
    ),
}


def _catalogue_record(detail: dict[str, Any], slug: str, plugin: str) -> bool | None:
    """Validate hydrated minimized metadata too; missing or malformed is unknown."""
    record = (detail.get(slug) or {}).get("plugin_catalogue", {}).get(plugin, {})
    if (record.get("available") is True
            and record.get("basis") == "current_public_catalogue"
            and record.get("status") in ("enterprise", "active")
            and record.get("enterprise") is (record["status"] == "enterprise")):
        return record["enterprise"]
    return None


def _inventory_counts(stack: dict[str, Any]) -> dict[str, int] | None:
    counts = stack.get("datasourceCnts")
    if not isinstance(counts, dict) or any(
        not isinstance(k, str) or not isinstance(v, int) or isinstance(v, bool) or v < 0
        for k, v in counts.items()
    ):
        return None
    return counts


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
        daily = s.get("dailyUserCnt")
        datasources = {k: v for k, v in (s.get("datasourceCnts") or {}).items()
                       if v and k not in EXCLUDED_DATASOURCES}
        signals = _signals_in_use(s)
        rows.append({
            " Stack": slug,
            "Region": s.get("regionSlug"),
            "Users (active)": active,
            "Users (daily)": daily,
            # Of the people with access, how many showed up today.
            "Stickiness": round(daily / active, 3) if active and daily is not None else None,
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

    # An estate total requires a measured count on every live stack. Zero is measured;
    # missing/null is not, and must not silently contribute zero to a total or denominator.
    active_total = (
        sum(s["currentActiveUsers"] for s in stacks)
        if stacks and all(s.get("currentActiveUsers") is not None for s in stacks) else None
    )
    daily_total = (
        sum(s["dailyUserCnt"] for s in stacks)
        if stacks and all(s.get("dailyUserCnt") is not None for s in stacks) else None
    )
    if active_total and daily_total is not None:
        metrics.append((
            "gcinsight_usage_stickiness_ratio", {},
            round(daily_total / active_total, 4),
        ))

    # Plugin adoption = stacks with at least one instance, not instance count. One stack with 12
    # Infinity datasources is not 12 stacks' worth of adoption.
    adoption: dict[str, int] = {}
    instances: dict[str, int] = {}
    inventory_measured = sum(_inventory_counts(s) is not None for s in stacks)
    inventory_complete = bool(stacks) and inventory_measured == len(stacks)
    for s in stacks:
        for name, count in (_inventory_counts(s) or {}).items():
            if not count or name in EXCLUDED_DATASOURCES:
                continue
            adoption[name] = adoption.get(name, 0) + 1
            instances[name] = instances.get(name, 0) + count
    # Vendor datasource types are discovered strings, not a fixed enum. They stay in the views below;
    # Mimir gets only scalar estate counts. The Synthetic Monitoring scalar preserves the established
    # provisioned-versus-active comparison without republishing its plugin id as a label value.
    if inventory_complete:
        metrics.append(("gcinsight_usage_datasource_types_distinct", {}, float(len(adoption))))
        metrics.append((
            "gcinsight_usage_synthetic_monitoring_datasource_stacks", {},
            float(adoption.get("synthetic-monitoring-datasource", 0)),
        ))

    catalogue_rows = []
    catalogue_by = {}
    for name in adoption:
        classifications = [
            _catalogue_record(stack_detail, str(s["slug"]), name)
            for s in stacks if (_inventory_counts(s) or {}).get(name, 0) > 0
        ]
        measured = [value for value in classifications if value is not None]
        # Partial or inconsistent catalogue joins cannot classify the whole plugin rollup.
        enterprise = (measured[0] if len(measured) == len(classifications)
                      and len(set(measured)) == 1 else None)
        row = {
            " Plugin": name,
            "Enterprise (current catalogue)": enterprise,
            "Stacks (measured)": adoption[name],
            "Configured instances (measured)": instances[name],
            "Catalogue stacks measured": len(measured),
            "Inventory stacks measured": inventory_measured,
            "Estate stacks": len(stacks),
            "Catalogue basis": "current_public_catalogue" if measured else "unknown",
        }
        catalogue_rows.append(row)
        catalogue_by[name] = row
    if not catalogue_rows and not inventory_complete:
        # A coverage-only row distinguishes unknown inventory from measured absence.
        catalogue_rows.append({
            " Plugin": None, "Enterprise (current catalogue)": None,
            "Stacks (measured)": None, "Configured instances (measured)": None,
            "Catalogue stacks measured": 0, "Inventory stacks measured": inventory_measured,
            "Estate stacks": len(stacks), "Catalogue basis": "unknown",
        })

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
        "usage_enterprise_catalogue": sorted(catalogue_rows, key=lambda r: r[" Plugin"] or ""),
        "usage_plugin_adoption": sorted(
            [
                {
                    " Plugin": name,
                    "Stacks": count,
                    "Share of estate %": round(100 * count / len(stacks), 1) if inventory_complete else None,
                    "Total instances": instances[name],
                    "Enterprise (current catalogue)": catalogue_by[name]["Enterprise (current catalogue)"],
                    "Catalogue stacks measured": catalogue_by[name]["Catalogue stacks measured"],
                    "Inventory stacks measured": inventory_measured,
                    "Estate stacks": len(stacks),
                }
                for name, count in adoption.items()
            ],
            key=lambda r: -r["Stacks"],
        ),
        "usage_datasource_inventory": sorted(
            [
                {
                    " Stack": str(stack.get("slug") or ""),
                    "Datasource type": name,
                    "Provisioned instances": int(count),
                    "Enterprise (current catalogue)": _catalogue_record(
                        stack_detail, str(stack["slug"]), name),
                    "Catalogue basis": (
                        "current_public_catalogue" if _catalogue_record(
                            stack_detail, str(stack["slug"]), name) is not None else "unknown"),
                }
                for stack in stacks
                for name, count in (_inventory_counts(stack) or {}).items()
                if count and name not in EXCLUDED_DATASOURCES
            ],
            key=lambda row: (row["Datasource type"], row[" Stack"]),
        ),
        # Provisioned, populated, and nobody logs in. The clearest "paid for, not used" list.
        "usage_dormant_stacks": sorted(
            [r for r in rows if r["Users (daily)"] == 0 and r["Users (active)"] > 0],
            key=lambda r: -(r["Dashboards"] or 0),
        ),
        "usage_summary": [{
            " Metric": "Stickiness (daily / active users, estate)",
            "Value": (
                round(daily_total / active_total, 3)
                if active_total and daily_total is not None
                else None
            ),
        }, {
            " Metric": "Active users",
            "Value": active_total,
        }, {
            " Metric": "Daily users",
            "Value": daily_total,
        }, {
            " Metric": "Datasource types in use (excl. auto-provisioned)",
            "Value": len(adoption) if inventory_complete else None,
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
