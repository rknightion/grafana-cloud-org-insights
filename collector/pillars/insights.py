"""Pillar J - dashboard and query usage, from each stack's own usage-insights datasource.

**What this answers that nothing else can.** Every other pillar measures what EXISTS: how many
dashboards, how many users, how much ingest. This one measures what is USED - which dashboards are
opened, by how many distinct people, which panels actually run queries, what fraction is served from
cache, and what errors readers hit. A stack with 400 dashboards and 3 that anyone opens looks healthy
everywhere else in this platform.

**It also measures public-dashboard exposure.** `publicDashboardUid` on a usage-insights event means a
dashboard was opened through a public share, with `userId="-1"` for an unauthenticated reader. The
separate enumeration input owns configured inventory; this pillar provides the observed-use count and
named activity list.

Every figure is over the same 24-hour window (`sources.usage_insights.WINDOW`), aggregated inside Loki
rather than here, and measured per stack with that stack's own read-only credential.

**Coverage is never assumed.** A stack with no credential yet, a datasource that is not provisioned, or
a token the API refuses each produce a row saying so. `insights_coverage` is the denominator for every
other figure on this pillar, and a percentage without it is meaningless.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from collector.coverage import Coverage
from collector.sources.usage_insights import WINDOW

# A per-stack cache ratio is only meaningful once a stack has run enough queries for the ratio to mean
# anything. Below this the figure swings between 0 and 100 on a handful of requests.
CACHE_RATIO_FLOOR = 100

# Rows in the per-stack detail table are ordered by views, so this only bounds the estate-wide
# top-dashboard list that draws from every stack's own top-N.
ESTATE_TOP_DASHBOARDS = 50

# The initial live sweep omitted the mandatory regional instance_id guard, so every Pillar J metric
# needs a clean epoch that dashboard selectors can require. Keep this on the whole pillar: even a
# figure that happened to look plausible in the bad sweep is not safe historical evidence.
METRIC_EPOCH = "2"

_STACK_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"), ("Views", "number"), ("Distinct viewers", "number"),
    ("Dashboards viewed", "number"), ("Dashboards provisioned", "number"),
    ("Viewed share %", "number"), ("Data requests", "number"),
    ("Identified panel requests", "number"), ("Panel identity coverage %", "number"),
    ("Distinct dashboard-panel pairs", "number"), ("Datasource types queried", "number"),
    ("Cache hit %", "number"), ("Request errors", "number"),
    ("Request error rate %", "number"),
    ("Public dashboard events", "number"), ("Anonymous views", "number"),
)

_PUBLIC_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"), ("Dashboard", "string"), ("Dashboard uid", "string"),
    ("Public uid", "string"), ("Events", "number"),
)

_TOP_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"), ("Dashboard", "string"), ("Folder", "string"),
    ("Dashboard uid", "string"), ("Views", "number"),
)

_COVERAGE_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Stack", "string"), ("State", "string"), ("Detail", "string"),
)

_DS_ROW_SCHEMA: tuple[tuple[str, str], ...] = (
    (" Datasource type", "string"), ("Data requests", "number"),
    ("Cumulative duration (ms)", "number"), ("Request errors", "number"),
    ("Stacks", "number"),
)

# Views where finding nothing is a legitimate state, so the dashboard renders an empty table rather
# than failing the whole build. `insights_public_dashboards` empty is the GOOD outcome.
VIEW_SCHEMAS: dict[str, tuple[tuple[str, str], ...]] = {
    "insights_dashboard_usage": _STACK_ROW_SCHEMA,
    "insights_public_dashboards": _PUBLIC_ROW_SCHEMA,
    "insights_top_dashboards": _TOP_ROW_SCHEMA,
    "insights_coverage": _COVERAGE_ROW_SCHEMA,
    "insights_datasource_types": _DS_ROW_SCHEMA,
}

# Why a stack has no figures. Split so "nobody has provisioned it yet" never reads as "it has no usage".
STATE_LABEL = {
    "no_credential": "no credential yet",
    "no_instance_id": "no instance id to filter on",
    "token_401": "credential refused",
    "forbidden_403": "permission refused",
    "datasource_absent": "usage-insights not provisioned",
    "http_error": "HTTP error",
    "transport_error": "unreachable",
    "malformed_response": "malformed usage-insights response",
}


def _ratio(part: float, whole: float) -> float | None:
    """None, never 0.0, when the denominator is absent. A zero would read as a measured 0%."""
    return round(100 * part / whole, 1) if whole else None


def build(
    stacks: list[dict[str, Any]],
    coverage: Coverage,
    insights: Mapping[str, Mapping[str, Any]] | None = None,
) -> tuple[list[tuple[str, dict[str, str], float]], dict[str, list[dict[str, Any]]]]:
    """Compose Pillar J. `insights` is the per-stack payload from `sources.usage_insights.probe_all`."""
    metrics: list[tuple[str, dict[str, str], float]] = []
    views: dict[str, list[dict[str, Any]]] = {}
    if insights is None:
        # Structurally unavailable without the daily input. Emit NOTHING rather than zeros: an hourly
        # tier writing 0 would overwrite the real figures the daily tier published.
        return metrics, views

    rows: list[dict[str, Any]] = []
    coverage_rows: list[dict[str, Any]] = []
    public_rows: list[dict[str, Any]] = []
    top_rows: list[dict[str, Any]] = []
    ds_counts: dict[str, dict[str, float]] = {}

    est = dict.fromkeys(
        ("views", "viewers", "dashboards_viewed", "public_events", "anonymous_views",
         "requests", "request_errors", "queries_total", "queries_cached",
         "panels_queried", "datasources_queried"), 0.0)
    # The DENOMINATOR for the headline adoption figure, and the only one not read off a
    # usage-insights event: it comes from the inventory, summed over the stacks that could be
    # measured. Without it "247 dashboards were opened" has no scale, and taking the estate's whole
    # dashboard count instead would divide by stacks this pillar never reached.
    est_provisioned = 0.0
    est_public_dashboards = 0.0
    est_identified_panel_requests = 0.0
    measured = with_views = with_public = 0

    # The LIVE inventory drives this, never the payload: a stack added since the last sweep gets an
    # honest "no credential yet" row, and a departed stack gets none at all.
    for stack in stacks:
        slug = str(stack.get("slug") or "")
        rec = (insights or {}).get(slug) or {}
        if not rec.get("available"):
            reason = str(rec.get("reason") or "not measured")
            coverage_rows.append({
                " Stack": slug,
                "State": STATE_LABEL.get(reason, reason),
                "Detail": str(rec.get("detail") or ""),
            })
            continue

        measured += 1
        provisioned = float(stack.get("dashboardCnt") or 0)
        est_provisioned += provisioned
        views_n = float(rec.get("views") or 0)
        requests = float(rec.get("requests") or 0)
        errors = float(rec.get("request_errors") or 0)
        q_total = float(rec.get("queries_total") or 0)
        q_cached = float(rec.get("queries_cached") or 0)
        identified_panel_requests = float(rec.get("panel_identity_requests") or 0)
        public = float(rec.get("public_events") or 0)
        public_dashboards = float(rec.get("public_dashboards_distinct") or 0)
        est_public_dashboards += public_dashboards
        est_identified_panel_requests += identified_panel_requests
        if views_n:
            with_views += 1
        if public_dashboards:
            with_public += 1

        for key in est:
            est[key] += float(rec.get(key) or 0)

        rows.append({
            " Stack": slug,
            "Views": int(views_n),
            "Distinct viewers": int(rec.get("viewers") or 0),
            "Dashboards viewed": int(rec.get("dashboards_viewed") or 0),
            "Dashboards provisioned": int(provisioned),
            "Viewed share %": _ratio(float(rec.get("dashboards_viewed") or 0), provisioned),
            "Data requests": int(requests),
            "Identified panel requests": int(identified_panel_requests),
            "Panel identity coverage %": _ratio(identified_panel_requests, requests),
            "Distinct dashboard-panel pairs": int(rec.get("panels_queried") or 0),
            "Datasource types queried": int(rec.get("datasources_queried") or 0),
            # Withheld below the floor: a ratio over a handful of requests swings wildly.
            "Cache hit %": _ratio(q_cached, q_total) if q_total >= CACHE_RATIO_FLOOR else None,
            "Request errors": int(errors),
            "Request error rate %": _ratio(errors, requests),
            "Public dashboard events": int(public),
            "Anonymous views": int(rec.get("anonymous_views") or 0),
        })

        for pub in rec.get("public_dashboards") or []:
            public_rows.append({
                " Stack": slug,
                "Dashboard": pub.get("dashboardName") or "(unnamed)",
                "Dashboard uid": pub.get("dashboardUid") or "",
                "Public uid": pub.get("publicDashboardUid") or "",
                "Events": int(pub.get("count") or 0),
            })
        for top in rec.get("top_dashboards") or []:
            top_rows.append({
                " Stack": slug,
                "Dashboard": top.get("dashboardName") or "(unnamed)",
                "Folder": top.get("folderName") or "(General)",
                "Dashboard uid": top.get("dashboardUid") or "",
                "Views": int(top.get("count") or 0),
            })
        stack_ds_types: set[str] = set()
        for ds in rec.get("datasource_types") or []:
            kind = ds.get("datasourceType") or "(unknown)"
            stack_ds_types.add(kind)
            entry = ds_counts.setdefault(
                kind, {"queries": 0.0, "duration_ms": 0.0, "errors": 0.0, "stacks": 0.0})
            entry["queries"] += float(ds.get("count") or 0)
        for ds in rec.get("datasource_duration_ms") or []:
            kind = ds.get("datasourceType") or "(unknown)"
            stack_ds_types.add(kind)
            entry = ds_counts.setdefault(
                kind, {"queries": 0.0, "duration_ms": 0.0, "errors": 0.0, "stacks": 0.0})
            entry["duration_ms"] += float(ds.get("count") or 0)
        for ds in rec.get("datasource_errors") or []:
            kind = ds.get("datasourceType") or "(unknown)"
            stack_ds_types.add(kind)
            entry = ds_counts.setdefault(
                kind, {"queries": 0.0, "duration_ms": 0.0, "errors": 0.0, "stacks": 0.0})
            entry["errors"] += float(ds.get("count") or 0)
        for kind in stack_ds_types:
            ds_counts[kind]["stacks"] += 1

        # --- per-stack metrics. The budget is a runaway backstop, not a design constraint, so the
        # dimensions a reader would want to trend or alert on are all emitted rather than rationed.
        for name, value in (
            ("views", views_n),
            ("viewers", float(rec.get("viewers") or 0)),
            ("viewed", float(rec.get("dashboards_viewed") or 0)),
            ("panel_queries", requests),
            ("query_errors", errors),
            ("public_events", public),
            ("anonymous_views", float(rec.get("anonymous_views") or 0)),
        ):
            metrics.append((f"gcinsight_dashboards_{name}", {"stack": slug}, value))
        if q_total >= CACHE_RATIO_FLOOR:
            metrics.append(("gcinsight_dashboards_cache_hit_ratio", {"stack": slug},
                            round(q_cached / q_total, 4)))

    views["insights_dashboard_usage"] = sorted(rows, key=lambda r: -r["Views"])
    views["insights_coverage"] = sorted(coverage_rows, key=lambda r: r[" Stack"])
    # Highest observed exposure first.
    views["insights_public_dashboards"] = sorted(public_rows, key=lambda r: -r["Events"])
    views["insights_top_dashboards"] = sorted(
        top_rows, key=lambda r: -r["Views"])[:ESTATE_TOP_DASHBOARDS]
    views["insights_datasource_types"] = sorted(
        ({" Datasource type": k, "Data requests": int(v["queries"]),
          "Cumulative duration (ms)": int(v["duration_ms"]),
          "Request errors": int(v["errors"]), "Stacks": int(v["stacks"])}
         for k, v in ds_counts.items()),
        key=lambda r: -r["Cumulative duration (ms)"],
    )

    # Coverage itself may be a measured zero. Everything derived from a measured stack is absent until
    # at least one stack succeeds; emitting structural zeroes would turn a total collection failure into
    # a confident statement that the estate has no usage.
    metrics.append(("gcinsight_dashboards_estate_stacks", {"kind": "measured"}, float(measured)))
    if measured:
        for key, value in est.items():
            metrics.append((f"gcinsight_dashboards_estate_{key}", {}, value))
        metrics.append(("gcinsight_dashboards_estate_provisioned", {}, est_provisioned))
        # The named view is deliberately bounded to top-N per stack. Its row count is not a total.
        metrics.append(("gcinsight_dashboards_estate_public", {}, est_public_dashboards))
        for kind, count in (("with_views", with_views),
                            ("with_public_dashboards", with_public)):
            metrics.append(("gcinsight_dashboards_estate_stacks", {"kind": kind}, float(count)))

    views["insights_summary"] = [
        {" Metric": f"Stacks measured (window {WINDOW})",
         "Value": f"{measured} of {len(stacks)}"},
        {" Metric": "Dashboard views", "Value": int(est["views"])},
        {" Metric": "Distinct viewers (summed per stack, not deduplicated across the org)",
         "Value": int(est["viewers"])},
        {" Metric": "Dashboards opened at least once", "Value": int(est["dashboards_viewed"])},
        {" Metric": "Dashboards provisioned across measured stacks",
         "Value": int(est_provisioned)},
        {" Metric": "Share of provisioned dashboards opened at least once %",
         "Value": _ratio(est["dashboards_viewed"], est_provisioned)},
        {" Metric": "Distinct public dashboards observed in use",
         "Value": int(est_public_dashboards)},
        {" Metric": "Anonymous dashboard views", "Value": int(est["anonymous_views"])},
        {" Metric": "Data requests", "Value": int(est["requests"])},
        {" Metric": "Data requests with dashboard and panel ids",
         "Value": int(est_identified_panel_requests)},
        {" Metric": "Panel identity coverage %",
         "Value": _ratio(est_identified_panel_requests, est["requests"])},
        {" Metric": "Data-request errors", "Value": int(est["request_errors"])},
        {" Metric": "Cache hit % across measured stacks",
         "Value": _ratio(est["queries_cached"], est["queries_total"])},
    ]
    # Apply the epoch at the one output seam so a future metric cannot accidentally rejoin the
    # contaminated unversioned history.
    metrics = [(name, {**labels, "version": METRIC_EPOCH}, value)
               for name, labels, value in metrics]
    return metrics, views
