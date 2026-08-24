"""Pillar A - estate & tenant health, and the shared per-stack view.

Pure functions from scan data to `(metrics, views)`. Metrics carry bounded labels only; anything
unbounded (slugs are bounded at 271 and are the primary key, so `stack` is allowed; names and versions
are not) goes into the views (SPEC §5.3).
"""

from __future__ import annotations

import datetime as dt
from typing import Any, Iterable

from collector.coverage import Coverage

# The build 258 of 271 stacks run. Anything else is drift worth a look.
def _modal(values: Iterable[str]) -> str | None:
    counts: dict[str, int] = {}
    for v in values:
        if v:
            counts[v] = counts.get(v, 0) + 1
    return max(counts, key=lambda k: counts[k]) if counts else None


def _age_days(iso: str | None, now: dt.datetime) -> float | None:
    if not iso:
        return None
    try:
        then = dt.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
    except ValueError:
        return None
    return round((now - then).total_seconds() / 86400, 1)


# Column spec for the per-stack row, and for every view that is a FILTERED SUBSET of it.
#
# Needed because a subset can legitimately be empty - an estate with no version drift, or no test
# leftover that bills, is the GOOD outcome - and `columns_for` on an empty view raises, which takes
# down the whole dashboard rather than one panel. Declared here rather than at the panel because the
# row shape belongs to this pillar; `tests/test_estate_schema.py` re-derives it from the live `estate`
# view so the two cannot drift.
ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"),
    ("Region", "string"),
    ("Cluster", "string"),
    ("Status", "string"),
    ("Dashboards", "number"),
    ("Alert rules", "number"),
    ("Users (active)", "number"),
    ("Users (billed)", "number"),
    ("Users (daily)", "number"),
    ("Admin share %", "number"),
    ("Active series", "number"),
    ("Age (days)", "number"),
    ("Idle (days)", "number"),
    ("Version drift", "boolean"),
    ("Delete protection", "boolean"),
    ("Test leftover", "boolean"),
    ("Created by", "string"),
    ("Updated by", "string"),
)

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "estate_leftovers_idle": ROW_SCHEMA,
    "estate_leftovers_billing": ROW_SCHEMA,
    "estate_drift": ROW_SCHEMA,
}


def _is_test_leftover(slug: str) -> bool:
    """Stack-creation automation leaks stacks.

    Test-prefixed slugs commonly come from stack-creation automation. The synthetic fixture preserves
    that prefix because it is the classification signal this function evaluates.

    The broad `test` prefix is deliberate. The views separate billed from idle leftovers because one
    is a cost conversation and the other is governance.
    """
    return slug.startswith("test")


def build(stacks: list[dict[str, Any]], coverage: Coverage, now: dt.datetime | None = None
          ) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    now = now or dt.datetime.now(dt.timezone.utc)
    modal_version = _modal(str(s.get("runningVersion") or "") for s in stacks)

    rows: list[dict[str, Any]] = []
    for s in stacks:
        slug = str(s["slug"])
        version = str(s.get("runningVersion") or "")
        users = s.get("currentActiveUsers") or 0
        admins = s.get("currentActiveAdminUsers") or 0
        rows.append({
            # Leading space forces the display order Infinity's backend parser would otherwise
            # alphabetise away (SPEC §7.4).
            " Stack": slug,
            "Region": s.get("regionSlug"),
            "Cluster": s.get("clusterSlug"),
            "Status": s.get("status"),
            "Dashboards": s.get("dashboardCnt") or 0,
            "Alert rules": s.get("alertCnt") or 0,
            "Users (active)": users,
            "Users (billed)": s.get("billingActiveUsers") or 0,
            "Users (daily)": s.get("dailyUserCnt") or 0,
            "Admin share %": round(100 * admins / users, 1) if users else None,
            "Active series": s.get("hmInstancePromCurrentActiveSeries") or 0,
            "Age (days)": _age_days(s.get("createdAt"), now),
            "Idle (days)": _age_days(s.get("updatedAt"), now),
            "Version drift": version != modal_version,
            "Delete protection": bool(s.get("deleteProtection")),
            "Test leftover": _is_test_leftover(slug),
            "Created by": s.get("createdBy") or None,
            "Updated by": s.get("updatedBy") or None,
        })

    active = [s for s in stacks if s.get("status") == "active"]
    leftovers = [s for s in stacks if _is_test_leftover(str(s["slug"]))]
    drifted = [s for s in stacks if str(s.get("runningVersion") or "") != modal_version]
    us_regions = [s for s in stacks if str(s.get("regionSlug") or "").startswith(("prod-us", "us-"))]

    metrics: list[tuple[str, dict[str, str], float]] = [
        ("gcinsight_estate_stacks", {"status": "total"}, float(len(stacks))),
        ("gcinsight_estate_stacks", {"status": "active"}, float(len(active))),
        ("gcinsight_estate_stacks", {"status": "paused"}, float(len(stacks) - len(active))),
        ("gcinsight_estate_test_leftover_stacks", {"kind": "idle"},
         float(len([s for s in leftovers if not (s.get("currentActiveUsers") or 0)]))),
        ("gcinsight_estate_test_leftover_stacks", {"kind": "billing"},
         float(len([s for s in leftovers if (s.get("currentActiveUsers") or 0)]))),
        ("gcinsight_estate_version_drift_stacks", {}, float(len(drifted))),
        ("gcinsight_estate_us_region_stacks", {}, float(len(us_regions))),
        ("gcinsight_estate_dashboards", {}, float(sum(s.get("dashboardCnt") or 0 for s in stacks))),
        ("gcinsight_estate_alert_rules", {}, float(sum(s.get("alertCnt") or 0 for s in stacks))),
        # Named separately and deliberately: only the billed figure is valid in a cost calculation.
        ("gcinsight_estate_active_users", {}, float(sum(s.get("currentActiveUsers") or 0 for s in stacks))),
        ("gcinsight_cost_billed_users", {}, float(sum(s.get("billingActiveUsers") or 0 for s in stacks))),
        ("gcinsight_estate_daily_users", {}, float(sum(s.get("dailyUserCnt") or 0 for s in stacks))),
    ]

    # Provisioned capability nobody switched on. Measured 2026-08-18: incident 0/271, machineLearning
    # 0/271, k6 98/271 - all three fields were already in every scan and none reached a metric.
    #
    # **These emit 0 rather than going absent, which is the opposite of this file's usual rule, and it is
    # deliberate.** A gap must be an absent series because a structural 0 from a tier that cannot compute
    # something overwrites a tier that can. This is not that: the inventory is present on every tier, the
    # question was asked, and the answer is genuinely none. The zero IS the finding, so the panel must be
    # able to render "0 of 272" rather than blank.
    #
    # `k6OrgId` is an id or null, not a 0/1 like the other two - a truthiness test covers both shapes,
    # where `== 1` would silently count nothing.
    #
    # **`kind="incident"` does NOT mean incident response is unused, and reading it that way is WRONG.**
    # It is gcom's flag for the legacy standalone Grafana Incident product. IRM and OnCall do not set it:
    # measured 2026-08-18, 20 stacks carry 11,549 OnCall alert groups and 2,905 user notifications while
    # gcom reports `incident: 0` AND `billingOnCallActiveUsers: 0` on every single one of them. Two
    # fields, two different products. The disproof is committed at
    # `testdata/usage-datasource-signals.json` key `irm_in_use`, and the value dashboard now carries the
    # OnCall count in the same tab so nobody reads the zero on its own.
    #
    # The same caution applies to all three: a flag proves the FLAG is unset, never that the org paid for
    # something and left it switched off. Do not present any of this as wasted spend. For real product
    # entitlement use `grafanacloud_product_activation_status` on the `grafanacloud-usage` datasource,
    # which these three booleans cannot see at all.
    for kind, enabled in (
        ("incident", sum(1 for s in stacks if s.get("incident"))),
        ("machine_learning", sum(1 for s in stacks if s.get("machineLearning"))),
        ("k6", sum(1 for s in stacks if s.get("k6OrgId"))),
    ):
        metrics.append(("gcinsight_estate_feature_stacks", {"kind": kind}, float(enabled)))
    for role, field in (("admin", "currentActiveAdminUsers"), ("editor", "currentActiveEditorUsers"),
                        ("viewer", "currentActiveViewerUsers")):
        metrics.append(
            ("gcinsight_estate_users_by_role", {"role": role},
             float(sum(s.get(field) or 0 for s in stacks)))
        )
    for region in sorted({str(s.get("regionSlug") or "unknown") for s in stacks}):
        metrics.append(
            ("gcinsight_estate_stacks_by_region", {"region": region},
             float(len([s for s in stacks if str(s.get("regionSlug") or "unknown") == region])))
        )
    metrics.extend(coverage.as_metrics())

    views = {
        "estate": sorted(rows, key=lambda r: -(r["Active series"] or 0)),
        # Split deliberately: a leftover with no users costs nothing and is a governance finding; one
        # with users is a cost finding. Conflating them was the error the review caught.
        "estate_leftovers_idle": [r for r in rows if r["Test leftover"] and not r["Users (active)"]],
        "estate_leftovers_billing": sorted(
            [r for r in rows if r["Test leftover"] and r["Users (active)"]],
            key=lambda r: -(r["Active series"] or 0),
        ),
        "estate_drift": [r for r in rows if r["Version drift"]],
    }
    return metrics, views
