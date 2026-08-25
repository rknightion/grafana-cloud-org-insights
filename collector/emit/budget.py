"""Series budget  -  the declared metric catalogue and the acceptance ceiling (PLAN 0.12, SPEC §5.3).

**Why this is code and not a prose table.** A prose budget cannot reliably account for fixed-enum
multipliers (a `{stack,kind}` metric costs the stack baseline times the enum size) or fail a build when a
pillar adds a label.
A table in a markdown file also cannot fail a build when a pillar quietly adds a label. This module is
the single source of the number, `tests/test_budget.py` asserts the pillars match what is declared here,
and `BUDGET.md` is generated from it (`python3 -m collector.emit.budget`).

**The denominator matters more than the total.** Every series lands on ONE configured write stack. Any
measured footprint must therefore be compared with that stack's own series at the same time, never with
the org total and never with a historical copy of either number. The budget is deliberately static, so
it does not embed a live denominator that will drift. The rule is:

    Per-stack detail belongs in an S3 view, which costs zero series. A per-stack METRIC has to justify
    itself by needing a time series  -  a trend, an alert, or a Grafana time-range interaction.

Per-stack metrics clear that bar only when the time dimension changes the decision. Point-in-time detail
belongs in a table panel over `views/`, so it is declared here with `store="view"` to record the decision
rather than leaving a future session to rediscover it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping

from collector import identity, technology_registry
from collector.emit.guard import ALLOWED_LABELS

# The acceptance ceiling. A runaway backstop, NOT a design constraint.
#
# At 100,000 the ceiling catches a genuine mistake: an unbounded label that slipped past the guard or a
# cross product nobody intended, without treating one deployment's current series count as policy.
#
# What still applies, because it is the thing that actually protects the stack:
#
# - **`guard.ALLOWED_LABELS` is unchanged.** An unbounded label KEY is still an error, not a warning.
#   That is the cardinality control; the ceiling never was.
# - **A per-stack metric still costs `STACK` series**, and one with an enum costs the product. Declare
#   it, know the number, and prefer a view when the answer is point-in-time rather than a trend.
# - **Every emitted metric must still appear in `CATALOGUE`**, so the total is always known rather than
#   discovered.
CEILING = 100_000

# A per-stack metric may carry at most one other label, and that enum may not exceed this. Wider
# breakdowns are what turn the stack baseline into five figures, and they are exactly the ones a table
# renders better.
MAX_PER_STACK_FANOUT = 4

Store = Literal["mimir", "view", "loki"]


@dataclass(frozen=True)
class MetricSpec:
    name: str
    pillar: str
    labels: Mapping[str, int] = field(default_factory=dict)
    store: Store = "mimir"
    phase: int = 1
    note: str = ""

    @property
    def series(self) -> int:
        """Series this spec contributes. A view or Loki stream contributes zero to the Mimir budget."""
        if self.store != "mimir":
            return 0
        n = 1
        for card in self.labels.values():
            n *= card
        return n


# Cardinality planning assumptions. They never become published estate denominators.
STACK = 271          # cardinality planning baseline only; never used as a published estate denominator
REGION = 8           # regionSlug
TIER = 4             # t1..t4
ROLE = 3             # admin/editor/viewer
SIGNAL = 6           # metrics/logs/traces/profiles/alerts/grafana
RUBRIC_VERSION = 2   # one live version, plus one during a rubric transition
PILLAR_J_EPOCHS = 2  # contaminated unversioned history plus the clean v2 epoch during transition
# Finding kinds in pillars/findings.py SPECS, with headroom for a few more. tests/test_findings.py
# asserts this covers the real count, so adding a kind without raising this fails the suite.
FINDING_KIND = 18
# Cardinality follows `len(hydrate.INPUT_OWNER)`; the test below the catalogue re-derives it so adding an
# input cannot silently leave this declaration stale.
INPUT = 15
# Assistant's chat taxonomy (pillars/ai.py). Declared at 8 x 8 = 64 to leave room for product additions
# without an unplanned series jump. Estate-wide ONLY; the per-stack cross product is a view.
CATEGORY = 8
SURFACE = 8
TECHNOLOGY = len(technology_registry.REGISTRY.entries)


CATALOGUE: tuple[MetricSpec, ...] = (
    # --- Scan health. Non-negotiable: the dead-man's switch (PLAN 1.8) alerts on these. ---
    MetricSpec("gcinsight_scan_stacks_total", "scan", {"tier": TIER}),
    MetricSpec("gcinsight_scan_stacks_scannable", "scan", {"tier": TIER}),
    MetricSpec("gcinsight_scan_stacks_scanned", "scan", {"tier": TIER}),
    MetricSpec("gcinsight_scan_coverage_ratio", "scan", {"tier": TIER}),
    MetricSpec("gcinsight_scan_stacks_failed", "scan", {"tier": TIER, "reason": 8},
               note="reason is a closed failure vocabulary: http_429, http_5xx, timeout, auth, ..."),
    MetricSpec("gcinsight_scan_stacks_skipped", "scan", {"tier": TIER, "reason": 3},
               note="paused, unresolvable, out_of_scope"),
    MetricSpec("gcinsight_scan_completed_timestamp_seconds", "scan", {"tier": TIER},
               note="PLAN 1.8  -  alerting is on ITS AGE, not on exit code"),
    MetricSpec("gcinsight_scan_duration_seconds", "scan", {"tier": TIER}),
    MetricSpec("gcinsight_carry_forward_series", "scan", {"tier": TIER},
               note="PLAN 5.3  -  how many slower-tier series the hourly tier republished"),
    MetricSpec("gcinsight_carry_forward_dropped_absent", "scan", {"tier": TIER},
               note="series NOT republished because their stack has left the estate. The estate is "
                    "re-discovered every run, so this going non-zero means a stack was decommissioned "
                    "between the last T3 and this T1  -  expected, and the proof the golden rule holds"),
    # Findings. One bounded gauge per finding KIND, so the finding TREND outlives log retention  -  which is
    # shorter than metric retention on every Grafana Cloud plan. The actionable detail (worst label name,
    # service-account name, stack slug) stays in Loki, where the cardinality guard permits it.
    #
    # Deliberately NOT also broken down by severity: severity is a property of the kind, so the second
    # breakdown is derivable from the first and would only buy series.
    MetricSpec("gcinsight_findings", "scan", {"kind": FINDING_KIND},
               note="count per finding kind, derived from the pillar views by pillars/findings.py. A kind "
                    "the running tier cannot compute is ABSENT, never 0"),
    MetricSpec("gcinsight_carry_forward_age_seconds", "scan", {"tier": TIER},
               note="age of the T3 state being carried. ALERT ON THIS  -  a stale carry-forward would "
                    "otherwise republish last month's scores as current, indefinitely"),

    # Cross-tier input hydration (PLAN 16.1). Every tier now composes from the full input set, pulling
    # what it did not gather from the owning tier's latest scan, so these two say WHICH input each
    # published figure really came from and how old it was. `_available` is the one to alert on: an
    # input that goes unavailable withholds its dependent views, so the symptom on the dashboard is a
    # table that stops advancing rather than one that goes to zero.
    MetricSpec("gcinsight_input_available", "scan", {"tier": TIER, "input": INPUT},
               note="1/0 per consumed input. 0 means the dependent views were WITHHELD this run"),
    MetricSpec("gcinsight_input_age_seconds", "scan", {"tier": TIER, "input": INPUT},
               note="age of the input the figures were computed from  -  NOT of the tier that ran. This is "
                    "what the per-dashboard freshness panels read; the old single 'Data age' showed T1's "
                    "timestamp on all eight dashboards and so claimed hourly freshness for 6-hourly data. "
                    "ABSENT rather than 0 when the input is unavailable: a 0 would read as 'just gathered'"),

    # --- Pillar A: estate rollups. The trend lines leadership reads. No stack label by design. ---
    MetricSpec("gcinsight_estate_stacks", "A", {"status": 3}),
    MetricSpec("gcinsight_estate_test_leftover_stacks", "A", {"kind": 2},
               note="idle vs billing  -  conflating them produced a bogus saving once already"),
    MetricSpec("gcinsight_estate_feature_stacks", "A", {"kind": 3},
               note="incident / machine_learning / k6  -  provisioned capability nobody switched on. "
                    "Emits 0 deliberately: a MEASURED zero is the "
                    "finding here, unlike a structural zero elsewhere. Proves the feature is off, NOT "
                    "that it is paid for"),
    MetricSpec("gcinsight_estate_version_drift_stacks", "A"),
    MetricSpec("gcinsight_estate_us_region_stacks", "A"),
    MetricSpec("gcinsight_estate_dashboards", "A"),
    MetricSpec("gcinsight_estate_alert_rules", "A"),
    MetricSpec("gcinsight_estate_active_users", "A"),
    MetricSpec("gcinsight_estate_daily_users", "A"),
    MetricSpec("gcinsight_estate_users_by_role", "A", {"role": ROLE}),
    MetricSpec("gcinsight_estate_stacks_by_region", "A", {"region": REGION}),

    # --- Per-stack metrics that earn a time series. ---
    MetricSpec("gcinsight_stack_active_series", "A", {"stack": STACK},
               note="the metrics cost driver; growth per stack is the platform team's core question"),
    MetricSpec("gcinsight_stack_billed_users", "B", {"stack": STACK},
               note="billingActiveUsers, NEVER currentActiveUsers. Named `stack_` "
                    "not `cost_` so it cannot collide with the estate rollup of the same quantity"),
    MetricSpec("gcinsight_maturity_score", "D", {"stack": STACK, "version": RUBRIC_VERSION},
               note="versioned so a rubric change is visible rather than silently rescoring history"),
    MetricSpec("gcinsight_adaptive_recommendations", "B", {"stack": STACK, "status": 2},
               note="pending vs applied  -  the largest remediable lever in the estate"),

    # --- Pillar B: cost rollups. ---
    MetricSpec("gcinsight_cost_billed_users", "B",
               note="estate total, no labels. Emitted by Pillar A today since it comes from the "
                    "same inventory pass; the pillar attribution here is about which dashboard reads it"),
    MetricSpec("gcinsight_cost_series_per_billed_user", "B",
               note="estate efficiency ratio; the per-stack version is a view column"),
    MetricSpec("gcinsight_cost_usage_by_signal", "B", {"signal": SIGNAL}),
    MetricSpec("gcinsight_cost_adaptive_rules_applied_total", "B"),
    MetricSpec("gcinsight_cost_stacks_without_adaptive", "B",
               note="stacks with active series but no applied Adaptive Metrics rules"),

    # Adaptive LOGS (PLAN 18.16).
    #
    # **There is deliberately NO applied-bytes metric.** The API reports each pattern's RESIDUAL volume,
    # so one already dropped at a high rate reports almost no bytes and `volume * configured/100`
    # computes to nothing - publishing it would understate the saving silently. The applied
    # half is measured by `grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second` on the
    # `grafanacloud-usage` datasource: a panel, no credential, and zero series against this budget.
    MetricSpec("gcinsight_cost_adaptivelogs_stacks_measured", "B",
               note="denominator: stacks whose plugin proxy answered, so a coverage drop is visible"),
    MetricSpec("gcinsight_cost_adaptivelogs_stacks_with_recommendations", "B"),
    MetricSpec("gcinsight_cost_adaptivelogs_stacks_none_applied", "B",
               note="the headline: recommendations held and nothing acted on"),
    MetricSpec("gcinsight_cost_adaptivelogs_recommendations_total", "B"),
    MetricSpec("gcinsight_cost_adaptivelogs_pending_total", "B"),
    MetricSpec("gcinsight_cost_adaptivelogs_pending_bytes_total", "B",
               note="bytes over the API's OWN UNSTATED window - never divide this into a rate. The "
                    "endpoint ignores every window parameter and names no period"),
    MetricSpec("gcinsight_cost_adaptivelogs_pending_bytes_unqueried", "B",
               note="the subset with no observed rule, query or dashboard references. It still needs "
                    "an owner review before a drop rule is applied"),
    MetricSpec("gcinsight_cost_adaptivelogs_pending_bytes", "B", {"stack": STACK},
               note="per stack, only where recommendations exist; the view carries the breakdown"),

    # --- Pillar C: consumer behaviour. ---
    MetricSpec("gcinsight_usage_stickiness_ratio", "C",
               note="estate daily/active; per-stack is a view column"),
    MetricSpec("gcinsight_usage_users_last_seen_bucket", "C", {"kind": 5},
               note="<7d, <30d, <90d, <180d, never"),
    MetricSpec("gcinsight_usage_plugin_adoption", "C", {"kind": 50},
               note="bounded headroom for datasource types; excludes "
                    "grafana-knowledgegraph-datasource because it is auto-provisioned rather than an "
                    "adoption decision"),
    MetricSpec("gcinsight_usage_stacks_by_signal", "C", {"signal": SIGNAL},
               note="signal PRESENCE from inventory usage fields, thresholded at USAGE_FLOOR. Protocol-adoption panels are live and query grafanacloud-usage directly, so they need no collector series. The synthetic two-series floor is deliberately excluded"),

    # --- Pillar D: rubric. ---
    MetricSpec("gcinsight_maturity_percentile", "D",
               {"kind": 3, "version": RUBRIC_VERSION}, note="median/p90/worst"),
    MetricSpec("gcinsight_maturity_stacks_by_tier", "D",
               {"kind": 4, "version": RUBRIC_VERSION}),
    MetricSpec("gcinsight_maturity_dimension_mean", "D",
               {"dimension": 9, "version": RUBRIC_VERSION},
               note="estate mean per rubric dimension  -  answers 'which dimension is the estate weakest "
                    "on', which the per-stack view cannot trend without a stack-by-dimension cross product. "
                    "Mean is over the stacks that SCORED that dimension, "
                    "excluding the four unscored reasons"),
    MetricSpec("gcinsight_maturity_unscored", "D",
               {"reason": 4, "version": RUBRIC_VERSION},
               note="paused / too_few_users / no_signal_above_floor / insufficient_rubric_coverage. "
                    "An unexplained 'unscored' on a dashboard reads as a collector bug"),

    # --- Pillar E: risk rollups. ---
    MetricSpec("gcinsight_risk_public_dashboards_total", "E", phase=2,
               note="RETIRED name, never emitted. Superseded twice: first by "
                    "gcinsight_dashboards_estate_public (Pillar J, event-derived), then by the "
                    "`_enumerated` family below, which counts the ones that EXIST. Kept declared so the "
                    "decision stays on the record. PLAN 0.4, 18.17"),

    # Public dashboards ENUMERATED per stack. This makes the configured inventory measurable even when
    # a dashboard has never been opened. The organisation decides the acceptable policy target.
    # `_measured` is not optional decoration. The endpoint answers 200 with a PERMISSION-FILTERED list
    # rather than 403, so a count taken without the role reads `totalCount: 0` - and on a zero-tolerance
    # policy a wrong zero reads as a PASS. The denominator is what makes the numerator trustworthy.
    MetricSpec("gcinsight_risk_public_dashboards_measured", "E",
               note="stacks the enumeration actually read. Never assume the rest are zero"),
    MetricSpec("gcinsight_risk_public_dashboards_enumerated", "E",
               note="public dashboards that EXIST across the measured stacks"),
    MetricSpec("gcinsight_risk_public_dashboards_enabled", "E",
               note="the subset live right now. A disabled one is still a configured share, one click "
                    "from live, so it counts towards the breach but not towards exposure"),
    MetricSpec("gcinsight_risk_public_dashboards_stacks", "E",
               note="how many stacks carry at least one - the number of owner conversations"),
    MetricSpec("gcinsight_risk_admin_heavy_stacks", "E", note="admin share above threshold"),
    MetricSpec("gcinsight_risk_org_members_admins", "E",
               note="Grafana.com org Admin membership count. Reported without a target or grade"),
    MetricSpec("gcinsight_risk_org_members_viewers", "E",
               note="Grafana.com org Viewer membership count. Reported without a target or grade"),
    MetricSpec("gcinsight_risk_org_members_staff_access", "E", {"status": 4},
               note="members by active / expired / none / unknown staff-access-window state. Identity "
                    "and expiry timestamps remain in the S3 view, never labels"),
    MetricSpec("gcinsight_risk_service_accounts_total", "E", {"kind": 2},
               note="extsvc (auto-provisioned) vs custom"),
    MetricSpec("gcinsight_risk_alert_routing_stacks_measured", "E",
               note="stacks whose alert-rule and contact-point provisioning endpoints both answered"),
    MetricSpec("gcinsight_risk_alert_rules_total", "E",
               note="rules across the measured alert-routing population"),
    MetricSpec("gcinsight_risk_alert_rules_active_inherited", "E",
               note="active rules with no direct receiver, therefore inheriting notification policy"),
    MetricSpec("gcinsight_risk_alert_rules_active_missing_receiver", "E",
               note="active rules naming a receiver absent from the provisioning contact-point list"),
    MetricSpec("gcinsight_risk_alert_rules_unverified_builtin", "E",
               note="rules naming grafana-default-email when that built-in is absent from provisioning; "
                    "unverified, not called broken"),
    MetricSpec("gcinsight_risk_stacks_without_delete_protection", "E",
               note="estate count, no labels  -  the per-stack risk detail is the view"),
    MetricSpec("gcinsight_risk_plugin_drift_stacks", "E"),
    MetricSpec("gcinsight_risk_collectors_total", "E",
               note="every REGISTRATION Fleet Management returns, unchanged so the series stays "
                    "continuous. Read it with the active and inactive splits below"),
    MetricSpec("gcinsight_risk_collectors_active", "E",
               note="registrations NOT marked inactive, i.e. the real fleet. ABSENT rather than zero on "
                    "a payload predating the split, because a 0 would say the estate runs no collectors"),
    MetricSpec("gcinsight_risk_collectors_inactive", "E",
               note="registrations for collectors that are gone. Ephemeral compute churns these: the id "
                    "embeds the hostname, so every pod reschedule creates one"),
    MetricSpec("gcinsight_stack_collectors_active", "E", {"stack": STACK},
               note="the per-stack half; use it to find registration concentration and churn"),
    MetricSpec("gcinsight_risk_pipelines_total", "E"),
    MetricSpec("gcinsight_risk_pipelines_enabled", "E",
               note="a disabled pipeline still describes a target set but configures nothing; the plain "
                    "pipeline count alone therefore overstates active configuration"),
    MetricSpec("gcinsight_risk_pipelines_generated", "E",
               note="SOURCE_TYPE_GRAFANA. The rest were hand-authored, which is the difference between "
                    "'onboarding created this' and 'a team owns this'"),
    MetricSpec("gcinsight_risk_collectors_unconfigured", "E",
               note="alive, registered, and targeted by no ENABLED pipeline - so receiving no "
                    "configuration. Also the matcher evaluator's sanity check"),
    MetricSpec("gcinsight_risk_fleet_matchers_unparsed", "E",
               note="pipeline matchers this platform cannot parse. Non-zero means at least one "
                    "'collectors targeted' figure is UNKNOWN rather than small"),
    MetricSpec("gcinsight_risk_stacks_pipelines_no_collectors", "E",
               note="stacks with provisioned pipelines but no active collectors"),

    # --- Pillar F: business value. Rollups only; this is a leadership surface. ---
    MetricSpec("gcinsight_value_unit_cost_per_billed_user", "F"),
    MetricSpec("gcinsight_value_adoption_ratio", "F", {"signal": SIGNAL}),
    MetricSpec("gcinsight_value_benchmark", "F", {"kind": 10},
               note="internal benchmarking: median/p90/worst across the dimensions that have data"),
    MetricSpec("gcinsight_value_savings_identified_series", "F",
               note="remediable series, summed from the per-metric reduction each Adaptive "
                    "recommendation declares under ?verbose=true. Emitted whenever T3 data is present"),
    MetricSpec("gcinsight_value_savings_unused_series", "F",
               note="the subset whose metrics appear in no observed rule, query or dashboard. It is "
                    "a prioritisation signal, not permission to apply without owner review"),
    MetricSpec("gcinsight_value_savings_identified_currency", "F",
               note="the same reduction priced with the deployment's own rate card. ABSENT, never "
                    "zero, when no rate card is supplied or no stack returned verbose counts"),
    MetricSpec("gcinsight_value_savings_unused_currency", "F",
               note="the unused-reference subset, priced. Same absence rule as above; still subject "
                    "to owner review"),

    # --- Pillar J: dashboard and query usage, from each stack's own usage-insights datasource. ---
    #
    # The seam the per-stack reader credential unlocked. Nothing else this platform reaches reports
    # what is USED rather than what EXISTS, and nothing else can see `publicDashboardUid` at all.
    MetricSpec("gcinsight_dashboards_views", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="dashboard opens in the window. The adoption signal - a stack with 400 dashboards "
                    "and 3 anyone opens looks healthy in every other pillar"),
    MetricSpec("gcinsight_dashboards_viewers", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="distinct userIds opening a dashboard. Per stack; NOT deduplicated across the org"),
    MetricSpec("gcinsight_dashboards_viewed", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="distinct dashboards opened at least once. Against inventory dashboardCnt this is "
                    "the provisioned-but-never-opened figure"),
    MetricSpec("gcinsight_dashboards_panel_queries", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="data-request events: panel queries actually run"),
    MetricSpec("gcinsight_dashboards_query_errors", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="data-request events carrying a non-empty error - what readers actually hit"),
    MetricSpec("gcinsight_dashboards_public_events", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="events carrying publicDashboardUid; this measures use, while the separate "
                    "enumeration input measures configured inventory"),
    MetricSpec("gcinsight_dashboards_anonymous_views", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="dashboard opens with userId=-1, an unauthenticated reader"),
    MetricSpec("gcinsight_dashboards_cache_hit_ratio", "J",
               {"stack": STACK, "version": PILLAR_J_EPOCHS},
               note="cachedQueries/totalQueries, 0-1. WITHHELD below CACHE_RATIO_FLOOR requests - a "
                    "ratio over a handful of queries swings between 0 and 1 and means nothing"),
    MetricSpec("gcinsight_dashboards_estate_views", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_viewers", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_dashboards_viewed", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_public_events", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_anonymous_views", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_requests", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_request_errors", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_queries_total", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_queries_cached", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_panels_queried", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_datasources_queried", "J",
               {"version": PILLAR_J_EPOCHS}),
    MetricSpec("gcinsight_dashboards_estate_provisioned", "J",
               {"version": PILLAR_J_EPOCHS},
               note="dashboards PROVISIONED across the measured stacks, from inventory rather than "
                    "from a usage-insights event. The denominator for the headline adoption share - "
                    "the estate's whole dashboard count would divide by stacks this pillar never "
                    "reached"),
    MetricSpec("gcinsight_dashboards_estate_public", "J",
               {"version": PILLAR_J_EPOCHS},
               note="distinct public dashboards observed in use during the collection window"),
    MetricSpec("gcinsight_dashboards_estate_stacks", "J",
               {"kind": 3, "version": PILLAR_J_EPOCHS},
               note="measured / with_views / with_public_dashboards"),

    MetricSpec("insights_dashboard_usage", "J", store="view", note="per-stack table"),
    MetricSpec("insights_public_dashboards", "J", store="view",
               note="observed activity list: stack, dashboard, publicDashboardUid, events"),
    MetricSpec("insights_top_dashboards", "J", store="view"),
    MetricSpec("insights_datasource_types", "J", store="view",
               note="which datasource types are actually QUERIED, not merely provisioned"),
    MetricSpec("insights_coverage", "J", store="view",
               note="the denominator: why a stack has no figures"),
    MetricSpec("insights_summary", "J", store="view"),

    MetricSpec("cost_adaptive_metric_recommendations", "B", store="view",
               note="bounded top-ten-per-stack Adaptive Metrics action queue; metric names stay out of labels"),

    MetricSpec("risk_alert_routing", "E", store="view",
               note="per-stack rule routing and contact-point coverage; point-in-time inventory"),
    MetricSpec("risk_alert_routing_findings", "E", store="view",
               note="bounded named rule drill-down; rule identity stays out of metric labels"),
    MetricSpec("risk_org_members", "E", store="view",
               note="clear-PII named org membership and staff-access-window drill-down"),
    MetricSpec("risk_fleet_attributes", "E", store="view",
               note="bounded active-collector version, OS, platform, source and type breakdowns"),
    MetricSpec("risk_fleet_pipelines", "E", store="view",
               note="named pipeline matcher reach; full Alloy contents are never retained"),

    # --- Declared as views, deliberately. Zero series. This half of the table is the decision record. ---
    MetricSpec("estate", "A", {"stack": STACK}, store="view",
               note="wide per-stack inventory: region, cluster, status, dashboards, alert rules, users by "
                    "role, admin share, age, idle, drift, delete protection, leftover, created/updated by"),
    MetricSpec("maturity_dimensions", "D", {"stack": STACK, "kind": 9}, store="view",
               note="a table shows every dimension's contribution; only the composite needs trending"),
    MetricSpec("risk_sa_and_token_inventory", "E", {"stack": STACK}, store="view",
               note="named service-account and token inventory stays out of metric labels"),
    MetricSpec("risk_admin_share_per_stack", "E", {"stack": STACK}, store="view"),
    MetricSpec("risk_plugin_version_drift", "E", {"stack": STACK}, store="view"),
    MetricSpec("cost_cardinality_outliers", "B", {"stack": STACK}, store="view",
               note="point-in-time stack and label-name drill-down for cardinality outliers"),
    MetricSpec("estate_leftovers_idle", "A", store="view",
               note="idle non-billing stack candidates; row count is deployment-specific"),
    MetricSpec("estate_leftovers_billing", "A", store="view",
               note="billing-active leftover candidates; row count is deployment-specific"),
    # --- Pillar I: Grafana Assistant (PLAN 17E). ------------------------------------------------
    #
    # THREE per-stack metrics, and each had to beat "is this already available on the write stack?".
    # Assistant users and AI tokens per stack are already in `grafanacloud-usage` against `stack_id`, so
    # they are NOT re-emitted; message count, the per-user token ratio and the machine-driven share exist
    # in no other datasource at all.
    MetricSpec("gcinsight_ai_messages", "I", {"stack": STACK},
               note="Assistant user messages in the 30-day window. Emitted for every stack whose "
                    "Assistant API was READ, zeros included, so an absent series still means "
                    "'not measured' and never 'not used'"),
    MetricSpec("gcinsight_ai_tokens_per_active_user", "I", {"stack": STACK},
               note="the outlier detector. ABSENT where there are no active users: the ratio is "
                    "undefined, and a zero would rank a dormant stack as the most efficient"),
    MetricSpec("gcinsight_ai_machine_share", "I", {"stack": STACK},
               note="share of CATEGORISED messages from a non-web surface (cli/a2a/automation/lodestone/"
                    "slack). Absent where nothing was categorised. Exists in no other datasource"),

    MetricSpec("gcinsight_ai_estate_messages", "I", {"category": CATEGORY, "surface": SURFACE},
               note="estate-wide category x surface, NO `stack` label  -  the per-stack cross product "
                    "belongs in the existing `ai_category_surface` view"),
    MetricSpec("gcinsight_ai_estate_category_combos", "I",
               note="how many category x surface combinations are in use. A drift detector: this rising "
                    "is Assistant adding to its taxonomy, and it explains a series increase before "
                    "somebody has to go looking for one"),
    MetricSpec("gcinsight_ai_estate_messages_total", "I"),
    MetricSpec("gcinsight_ai_estate_messages_uncategorised", "I",
               note="messages carrying no category. The honesty metric: no category chart may be "
                    "normalised to total messages"),
    MetricSpec("gcinsight_ai_estate_users", "I", note="sum of per-stack Assistant active users"),
    MetricSpec("gcinsight_ai_estate_tokens", "I"),
    MetricSpec("gcinsight_ai_estate_stacks", "I", {"kind": 4},
               note="measured / with_usage / with_tenant_config  -  the enablement headline is the gap "
                    "between usage and tenant configuration"),
    MetricSpec("gcinsight_ai_estate_tenant_objects", "I", {"kind": 4},
               note="TENANT-scoped skills / rules / automations / integrations. User-scoped objects are "
                    "invisible to any identity but their owner and are not even countable, so this can "
                    "never be a total"),
    MetricSpec("gcinsight_ai_estate_investigations", "I", {"kind": 2},
               note="created by assistant vs by user. The INVENTORY is not collectable; these counts are"),

    # Credential coverage for the per-stack reader (PLAN 17D). Emitted by the tier that gathers the
    # Assistant input, because that tier is the one that actually proved each credential works.
    MetricSpec("gcinsight_stacks_provisioned", "I"),
    MetricSpec("gcinsight_stacks_missing_credential", "I",
               note="count of provisionable stacks with no working credential. NOT the alert: a count "
                    "above zero is normal for hours after the organisation creates a stack"),
    MetricSpec("gcinsight_missing_credential_age_seconds", "I",
               note="age of the OLDEST individual gap, from emit/gapstate.py. THIS is the alert, at 48h. "
                    "A `for` clause on the count never resets while stacks keep appearing, so it would "
                    "fire having never seen one gap last two days. ABSENT when there is no gap"),

    MetricSpec("ai_assistant", "I", {"stack": STACK}, store="view",
               note="the wide per-stack table: users, days active, messages, categorised/uncategorised, "
                    "tokens split chat vs investigation, tenant object counts, and why a stack was not "
                    "measured"),
    MetricSpec("ai_category_surface", "I", {"stack": STACK, "kind": 21}, store="view",
               note="per-stack human-vs-machine detail; the bounded view avoids a stack-by-taxonomy "
                    "metric cross product"),
    MetricSpec("ai_tenant_config", "I", {"stack": STACK}, store="view",
               note="one row per tenant skill/rule/automation/MCP integration: name, enabled, scope, "
                    "createdBy, and `authenticationFailed` for MCPs. Bodies, rule content, MCP URLs and "
                    "headers are NOT collected"),
    MetricSpec("ai_credential_coverage", "I", {"stack": STACK}, store="view",
               note="which stacks lack a working reader credential, since when, and whether that is "
                    "actionable  -  paused and opted-out stacks must read as skipped, not as failures"),
    MetricSpec("ai_enablement_gap", "I", store="view",
               note="stacks with material Assistant use and no tenant configuration"),
    MetricSpec("ai_token_outliers", "I", store="view"),
    MetricSpec("ai_mcp_auth_failed", "I", store="view",
               note="tenant MCP integrations whose last authentication failed"),
    MetricSpec("ai_config_disabled", "I", store="view",
               note="rules/automations/integrations that exist but are switched off. `enabled` is absent "
                    "on skills, so only an explicit false counts  -  unknown is not disabled"),
    MetricSpec("ai_summary", "I", store="view"),

    MetricSpec("usage_query_cost_attribution", "C", {"stack": STACK}, store="view", phase=2),
    MetricSpec("public_dashboard_inventory", "E", {"stack": STACK}, store="view", phase=3,
               note="complete configured public-dashboard inventory for comparison with local policy"),

    # --- Pillar K: affirmative observed estate and coverage depth. ---
    MetricSpec("gcinsight_coverage_stacks_measured", "K",
               note="stacks whose atomic four-signal inventory succeeded"),
    MetricSpec("gcinsight_coverage_stack_services", "K", {"stack": STACK},
               note="application population from the canonical service_name union; full discovered "
                    "count before the view's top-N bound"),
    MetricSpec("gcinsight_coverage_stack_technologies", "K", {"stack": STACK},
               note="technologies present through versioned sentinel matching"),
    MetricSpec("gcinsight_coverage_stack_clusters", "K", {"stack": STACK},
               note="distinct explicitly-windowed Mimir cluster label values"),
    MetricSpec("gcinsight_coverage_services_by_depth", "K", {"kind": 4},
               note="service assets carrying exactly 1, 2, 3 or 4 canonical signals"),
    MetricSpec("gcinsight_coverage_services_by_signal", "K", {"kind": 4},
               note="service assets carrying canonical metrics, logs, traces or profiles identity"),
    MetricSpec("gcinsight_coverage_technology_stacks", "K", {"kind": TECHNOLOGY},
               note="one bounded registry enum per technology; value is measured stacks present"),
    MetricSpec("gcinsight_coverage_stacks_by_technology_count", "K", {"kind": 4},
               note="measured stacks detecting 0, 1, 2-4 or 5+ registry technologies"),
    MetricSpec("gcinsight_coverage_metric_names", "K", {"kind": 2},
               note="matched vs unmatched metric-name evidence; unmatched is a registry backlog, "
                    "never a coverage share"),
    MetricSpec("gcinsight_coverage_service_identity", "K", {"kind": 3},
               note="canonical, legacy-only and overlap counts; generic service is never silently "
                    "promoted to service_name"),
    MetricSpec("gcinsight_coverage_service_population", "K", {"kind": 3},
               note="application, platform and infrastructure-unit populations; every discovered "
                    "identity is counted exactly once"),
    MetricSpec("gcinsight_coverage_unscored", "K", {"component": 8, "reason": 7},
               note="bounded component/reason counts; product absence and unavailable evidence are "
                    "excluded from the score rather than published as failed coverage"),
    MetricSpec("gcinsight_coverage_service_completeness_mean", "K", {"version": 2},
               note="mean over non-ephemeral services with at least four applicable components"),
    MetricSpec("gcinsight_coverage_service_applicable_components_mean", "K", {"version": 2},
               note="mean score denominator over exactly the same services as completeness"),
    MetricSpec("gcinsight_coverage_capability_gap", "K", {"kind": 10},
               note="provisioned or population-eligible stacks with no measured use, by a fixed "
                    "capability enum. Deliberately emits measured zero gaps on the adoption surface"),
    MetricSpec("coverage_service_register", "K", {"stack": STACK}, store="view",
               note="top-N named services with signal depth and explicit alert/dashboard metadata"),
    MetricSpec("coverage_technology_register", "K", {"stack": STACK, "kind": TECHNOLOGY}, store="view",
               note="stack x technology is current-state identity detail, not a time series"),
    MetricSpec("coverage_metric_name_register", "K", {"stack": STACK}, store="view",
               note="metric names and their registry classification; names never become labels"),
    MetricSpec("coverage_cluster_register", "K", {"stack": STACK}, store="view",
               note="named observed clusters; names never become labels"),
    MetricSpec("coverage_legacy_service_register", "K", {"stack": STACK}, store="view",
               note="generic Mimir service values retained separately as legacy identity evidence"),
    MetricSpec("coverage_summary", "K", {"stack": STACK}, store="view",
               note="per-stack counts, registry version, truncation and unmatched-name backlog"),
    MetricSpec("coverage_capability_adoption", "K", {"kind": 10}, store="view",
               note="population, used and opportunity counts with the denominator basis and next step"),
    MetricSpec("coverage_capability_opportunities", "K", {"stack": STACK, "kind": 10}, store="view",
               note="named call list ranked by active series; stack identity never becomes a new metric"),
)


class BudgetExceeded(ValueError):
    """The declared catalogue does not fit the ceiling."""


class BadShape(ValueError):
    """A spec breaks the per-stack fan-out rule."""


def check_shape(spec: MetricSpec) -> None:
    """Enforce the allow-list and the per-stack fan-out rule. Views are exempt from fan-out."""
    for key in spec.labels:
        if key not in ALLOWED_LABELS:
            raise BadShape(f"{spec.name}: label {key!r} is not in the guard's allow-list")
    if spec.store != "mimir" or "stack" not in spec.labels:
        return
    others = {k: v for k, v in spec.labels.items() if k != "stack"}
    if len(others) > 1:
        raise BadShape(
            f"{spec.name}: {len(others)} labels alongside `stack` ({sorted(others)}). A per-stack "
            f"metric may carry at most one; put the breakdown in a view."
        )
    for key, card in others.items():
        if card > MAX_PER_STACK_FANOUT:
            raise BadShape(
                f"{spec.name}: `stack` x `{key}`({card}) = {spec.series} series. Fan-out above "
                f"{MAX_PER_STACK_FANOUT} belongs in a view, not Mimir."
            )


def total(specs: Iterable[MetricSpec] = CATALOGUE, *, phase: int | None = None) -> int:
    return sum(s.series for s in specs if phase is None or s.phase <= phase)


def by_pillar(specs: Iterable[MetricSpec] = CATALOGUE) -> dict[str, int]:
    out: dict[str, int] = {}
    for s in specs:
        out[s.pillar] = out.get(s.pillar, 0) + s.series
    return out


def check_budget(specs: Iterable[MetricSpec] = CATALOGUE) -> int:
    specs = tuple(specs)
    for s in specs:
        check_shape(s)
    n = total(specs)
    if n > CEILING:
        raise BudgetExceeded(f"declared catalogue is {n} series, ceiling is {CEILING}")
    return n


def render_table() -> str:
    """Generate BUDGET.md. Regenerate with `python3 -m collector.emit.budget`."""
    mimir = [s for s in CATALOGUE if s.store == "mimir"]
    views = [s for s in CATALOGUE if s.store != "mimir"]
    n = total()
    lines = [
        "# Series budget",
        "",
        "**Generated from `collector/emit/budget.py`  -  do not hand-edit.**",
        "Regenerate: `python3 -m collector.emit.budget > BUDGET.md`",
        "",
        "## Declared capacity",
        "",
        "| | Series |",
        "|---|---:|",
        f"| **Declared (all phases)** | **{n:,}** |",
        f"| Phase 1 only | {total(phase=1):,} |",
        f"| Runaway ceiling | {CEILING:,} |",
        "",
        "Everything lands on the configured write stack alone. Compare the measured platform footprint "
        "with that stack's own series over the same range; the org total is never the denominator. The 100,000 "
        "ceiling is a runaway backstop, not a target and not a licence for unbounded labels.",
        "",
        "**This table is declared capacity, not the measured footprint  -  do not quote it as live use.** "
        "Declared capacity reserves every bounded enum at its ceiling and therefore exceeds the series "
        "present at a particular instant. Re-measure with a range query and a matching denominator before "
        "reporting footprint; never copy a measured count into this generated document.",
        "",
        "## By pillar",
        "",
        "| Pillar | Mimir series |",
        "|---|---|",
    ]
    for pillar, count in sorted(by_pillar().items()):
        lines.append(f"| {pillar} | {count:,} |")
    lines += [
        f"| **Total** | **{n:,}** |",
        "",
        "## Metrics",
        "",
        "| Metric | Pillar | Labels | Series | Phase | Note |",
        "|---|---|---|---|---|---|",
    ]
    for s in sorted(mimir, key=lambda s: (-s.series, s.name)):
        labels = ", ".join(f"`{k}`({v})" for k, v in s.labels.items()) or " - "
        lines.append(f"| `{s.name}` | {s.pillar} | {labels} | {s.series:,} | {s.phase} | {s.note} |")
    lines += [
        "",
        "## Deliberately views, not metrics",
        "",
        "Each row is a decision: the data is per-stack detail a table panel renders from `views/`, and "
        "emitting it would cost the series in the third column for a trend nobody asked for.",
        "",
        "| View | Pillar | Series if emitted | Phase | Why a view |",
        "|---|---|---|---|---|",
    ]
    for s in sorted(views, key=lambda s: s.name):
        would = 1
        for card in s.labels.values():
            would *= card
        lines.append(f"| `{s.name}` | {s.pillar} | {would:,} | {s.phase} | {s.note} |")
    lines += [
        "",
        "## Rules this table enforces",
        "",
        f"- A per-stack metric carries **at most one** other label, and its enum is **≤ "
        f"{MAX_PER_STACK_FANOUT}**. `stack` x `kind`(10) is 2,710 series  -  that is a table.",
        "- A per-stack time series must carry a bounded, actionable trend. Identity-bearing or wide "
        "cross-product detail belongs in a view, even under the relaxed total ceiling.",
        "- Label keys must be in `collector/emit/guard.py`'s allow-list. The guard is the runtime gate; "
        "this is the design-time one.",
        "",
    ]
    return identity.replace_metric_text("\n".join(lines))


if __name__ == "__main__":
    check_budget()
    print(render_table())
