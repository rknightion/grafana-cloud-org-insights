"""Pillar J's bounded, identity-bearing S3 views.

These tables deliberately emit no metrics: dashboard and datasource identities are unbounded and
belong in S3, not in Mimir labels.  The live estate inventory drives both joins; source payloads are
left-join lookups only.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

Metrics = list[tuple[str, dict[str, str], float]]
Views = dict[str, list[dict[str, Any]]]

DASHBOARD_VIEW = "insights_dashboard_opening_31d"
QUERY_COST_VIEW = "insights_datasource_query_cost"

VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    DASHBOARD_VIEW: (
        (" Stack", "string"), ("Dashboard", "string"), ("Folder", "string"),
        ("Dashboard uid", "string"), ("State", "string"), ("Views (31d)", "number"),
        ("Coverage detail", "string"),
    ),
    QUERY_COST_VIEW: (
        (" Stack", "string"), ("Datasource", "string"), ("Datasource uid", "string"),
        ("Datasource type", "string"), ("State", "string"),
        ("Cumulative duration (ms)", "number"), ("Cache hit %", "number"),
        ("Coverage detail", "string"),
    ),
}


def _dashboard_rows(
    stacks: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        record = payload.get(slug) or {}
        if not record.get("available"):
            # The inventory itself is unknown, so there is no dashboard identity to invent. Source
            # coverage rejects an estate-wide failure; a small number of per-stack gaps remain visible.
            rows.append({
                " Stack": slug,
                "Dashboard": "(inventory unavailable)",
                "Folder": "",
                "Dashboard uid": "",
                "State": "unknown",
                "Views (31d)": None,
                "Coverage detail": ": ".join(
                    part for part in (
                        str(record.get("reason") or "inventory unavailable"),
                        str(record.get("detail") or ""),
                    ) if part
                ),
            })
            continue

        activity_available = bool(record.get("activity_available"))
        opened = {
            str(item.get("dashboardUid") or ""): int(item.get("count") or 0)
            for item in record.get("opened") or []
            if str(item.get("dashboardUid") or "")
        }
        activity_detail = ": ".join(
            part for part in (
                str(record.get("activity_reason") or ""),
                str(record.get("activity_detail") or ""),
            ) if part
        )
        for dashboard in record.get("dashboards") or []:
            uid = str(dashboard.get("uid") or "")
            views = opened.get(uid, 0) if activity_available else None
            rows.append({
                " Stack": slug,
                "Dashboard": str(dashboard.get("title") or "(untitled)"),
                "Folder": str(dashboard.get("folder") or "(General)"),
                "Dashboard uid": uid,
                "State": ("opened" if views else "unopened") if activity_available else "unknown",
                "Views (31d)": views,
                "Coverage detail": "" if activity_available else activity_detail,
            })
    return sorted(rows, key=lambda row: (row["State"] != "unopened", row[" Stack"], row["Dashboard"]))


def _query_cost_rows(
    stacks: Sequence[Mapping[str, Any]],
    payload: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        record = payload.get(slug) or {}
        if not record.get("available"):
            rows.append({
                " Stack": slug,
                "Datasource": "(query cost unavailable)",
                "Datasource uid": "",
                "Datasource type": "",
                "State": "unknown",
                "Cumulative duration (ms)": None,
                "Cache hit %": None,
                "Coverage detail": ": ".join(
                    part for part in (
                        str(record.get("reason") or "query cost unavailable"),
                        str(record.get("detail") or ""),
                    ) if part
                ),
            })
            continue
        by_uid = {
            str(item.get("uid") or ""): item
            for item in record.get("datasources") or []
            if str(item.get("uid") or "")
        }
        for cost in record.get("costs") or []:
            uid = str(cost.get("datasourceUid") or "")
            datasource = by_uid.get(uid) or {}
            ratio = cost.get("cache_hit_ratio")
            rows.append({
                " Stack": slug,
                "Datasource": str(datasource.get("name") or "(unresolved uid)"),
                "Datasource uid": uid,
                "Datasource type": str(
                    datasource.get("type") or cost.get("datasourceType") or "(unknown)"
                ),
                "State": "measured",
                "Cumulative duration (ms)": int(cost.get("cost_ms") or 0),
                "Cache hit %": None if ratio is None else round(float(ratio) * 100, 1),
                "Coverage detail": "",
            })
    return sorted(
        rows,
        key=lambda row: (
            row["State"] == "unknown",
            -(row["Cumulative duration (ms)"] or 0),
            row[" Stack"],
        ),
    )


def build(
    stacks: Sequence[Mapping[str, Any]],
    *,
    dashboard_inventory: Mapping[str, Mapping[str, Any]] | None = None,
    datasource_query_cost: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[Metrics, Views]:
    metrics: Metrics = []
    views: Views = {}
    if dashboard_inventory is not None:
        views[DASHBOARD_VIEW] = _dashboard_rows(stacks, dashboard_inventory)
    if datasource_query_cost is not None:
        views[QUERY_COST_VIEW] = _query_cost_rows(stacks, datasource_query_cost)
    return metrics, views
