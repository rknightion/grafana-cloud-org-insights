# Series budget

**Generated from `collector/emit/budget.py`  -  do not hand-edit.**
Regenerate: `python3 -m collector.emit.budget > BUDGET.md`

## Declared capacity

| | Series |
|---|---:|
| **Declared (all phases)** | **7,828** |
| Phase 1 only | 7,827 |
| Runaway ceiling | 100,000 |

Everything lands on the configured write stack alone. Compare the measured platform footprint with that stack's own series over the same range; the org total is never the denominator. The 100,000 ceiling is a runaway backstop, not a target and not a licence for unbounded labels.

**This table is declared capacity, not the measured footprint  -  do not quote it as live use.** Declared capacity reserves every bounded enum at its ceiling and therefore exceeds the series present at a particular instant. Re-measure with a range query and a matching denominator before reporting footprint; never copy a measured count into this generated document.

## By pillar

| Pillar | Mimir series |
|---|---|
| A | 296 |
| B | 1,101 |
| C | 62 |
| D | 582 |
| E | 301 |
| F | 21 |
| I | 895 |
| J | 4,368 |
| scan | 202 |
| **Total** | **7,828** |

## Metrics

| Metric | Pillar | Labels | Series | Phase | Note |
|---|---|---|---|---|---|
| `gcinsight_adaptive_recommendations` | B | `stack`(271), `status`(2) | 542 | 1 | pending vs applied  -  the largest remediable lever in the estate |
| `gcinsight_dashboards_anonymous_views` | J | `stack`(271), `version`(2) | 542 | 1 | dashboard opens with userId=-1, an unauthenticated reader |
| `gcinsight_dashboards_cache_hit_ratio` | J | `stack`(271), `version`(2) | 542 | 1 | cachedQueries/totalQueries, 0-1. WITHHELD below CACHE_RATIO_FLOOR requests - a ratio over a handful of queries swings between 0 and 1 and means nothing |
| `gcinsight_dashboards_panel_queries` | J | `stack`(271), `version`(2) | 542 | 1 | data-request events: panel queries actually run |
| `gcinsight_dashboards_public_events` | J | `stack`(271), `version`(2) | 542 | 1 | events carrying publicDashboardUid; this measures use, while the separate enumeration input measures configured inventory |
| `gcinsight_dashboards_query_errors` | J | `stack`(271), `version`(2) | 542 | 1 | data-request events carrying a non-empty error - what readers actually hit |
| `gcinsight_dashboards_viewed` | J | `stack`(271), `version`(2) | 542 | 1 | distinct dashboards opened at least once. Against inventory dashboardCnt this is the provisioned-but-never-opened figure |
| `gcinsight_dashboards_viewers` | J | `stack`(271), `version`(2) | 542 | 1 | distinct userIds opening a dashboard. Per stack; NOT deduplicated across the org |
| `gcinsight_dashboards_views` | J | `stack`(271), `version`(2) | 542 | 1 | dashboard opens in the window. The adoption signal - a stack with 400 dashboards and 3 anyone opens looks healthy in every other pillar |
| `gcinsight_maturity_score` | D | `stack`(271), `version`(2) | 542 | 1 | versioned so a rubric change is visible rather than silently rescoring history |
| `gcinsight_ai_machine_share` | I | `stack`(271) | 271 | 1 | share of CATEGORISED messages from a non-web surface (cli/a2a/automation/lodestone/slack). Absent where nothing was categorised. Exists in no other datasource |
| `gcinsight_ai_messages` | I | `stack`(271) | 271 | 1 | Assistant user messages in the 30-day window. Emitted for every stack whose Assistant API was READ, zeros included, so an absent series still means 'not measured' and never 'not used' |
| `gcinsight_ai_tokens_per_active_user` | I | `stack`(271) | 271 | 1 | the outlier detector. ABSENT where there are no active users: the ratio is undefined, and a zero would rank a dormant stack as the most efficient |
| `gcinsight_cost_adaptivelogs_pending_bytes` | B | `stack`(271) | 271 | 1 | per stack, only where recommendations exist; the view carries the breakdown |
| `gcinsight_stack_active_series` | A | `stack`(271) | 271 | 1 | the metrics cost driver; growth per stack is the platform team's core question |
| `gcinsight_stack_billed_users` | B | `stack`(271) | 271 | 1 | billingActiveUsers, NEVER currentActiveUsers. Named `stack_` not `cost_` so it cannot collide with the estate rollup of the same quantity |
| `gcinsight_stack_collectors_active` | E | `stack`(271) | 271 | 1 | the per-stack half; use it to find registration concentration and churn |
| `gcinsight_ai_estate_messages` | I | `category`(8), `surface`(8) | 64 | 1 | estate-wide category x surface, NO `stack` label  -  the per-stack cross product belongs in the existing `ai_category_surface` view |
| `gcinsight_input_age_seconds` | scan | `tier`(4), `input`(13) | 52 | 1 | age of the input the figures were computed from  -  NOT of the tier that ran. This is what the per-dashboard freshness panels read; the old single 'Data age' showed T1's timestamp on all eight dashboards and so claimed hourly freshness for 6-hourly data. ABSENT rather than 0 when the input is unavailable: a 0 would read as 'just gathered' |
| `gcinsight_input_available` | scan | `tier`(4), `input`(13) | 52 | 1 | 1/0 per consumed input. 0 means the dependent views were WITHHELD this run |
| `gcinsight_usage_plugin_adoption` | C | `kind`(50) | 50 | 1 | bounded headroom for datasource types; excludes grafana-knowledgegraph-datasource because it is auto-provisioned rather than an adoption decision |
| `gcinsight_scan_stacks_failed` | scan | `tier`(4), `reason`(8) | 32 | 1 | reason is a closed failure vocabulary: http_429, http_5xx, timeout, auth, ... |
| `gcinsight_findings` | scan | `kind`(18) | 18 | 1 | count per finding kind, derived from the pillar views by pillars/findings.py. A kind the running tier cannot compute is ABSENT, never 0 |
| `gcinsight_maturity_dimension_mean` | D | `dimension`(9), `version`(2) | 18 | 1 | estate mean per rubric dimension  -  answers 'which dimension is the estate weakest on', which the per-stack view cannot trend without a stack-by-dimension cross product. Mean is over the stacks that SCORED that dimension, excluding the four unscored reasons |
| `gcinsight_scan_stacks_skipped` | scan | `tier`(4), `reason`(3) | 12 | 1 | paused, unresolvable, out_of_scope |
| `gcinsight_value_benchmark` | F | `kind`(10) | 10 | 1 | internal benchmarking: median/p90/worst across the dimensions that have data |
| `gcinsight_estate_stacks_by_region` | A | `region`(8) | 8 | 1 |  |
| `gcinsight_maturity_stacks_by_tier` | D | `kind`(4), `version`(2) | 8 | 1 |  |
| `gcinsight_maturity_unscored` | D | `reason`(4), `version`(2) | 8 | 1 | paused / too_few_users / no_signal_above_floor / insufficient_rubric_coverage. An unexplained 'unscored' on a dashboard reads as a collector bug |
| `gcinsight_cost_usage_by_signal` | B | `signal`(6) | 6 | 1 |  |
| `gcinsight_dashboards_estate_stacks` | J | `kind`(3), `version`(2) | 6 | 1 | measured / with_views / with_public_dashboards |
| `gcinsight_maturity_percentile` | D | `kind`(3), `version`(2) | 6 | 1 | median/p90/worst |
| `gcinsight_usage_stacks_by_signal` | C | `signal`(6) | 6 | 1 | signal PRESENCE from inventory usage fields, thresholded at USAGE_FLOOR. Protocol-adoption panels are live and query grafanacloud-usage directly, so they need no collector series. The synthetic two-series floor is deliberately excluded |
| `gcinsight_value_adoption_ratio` | F | `signal`(6) | 6 | 1 |  |
| `gcinsight_usage_users_last_seen_bucket` | C | `kind`(5) | 5 | 1 | <7d, <30d, <90d, <180d, never |
| `gcinsight_ai_estate_stacks` | I | `kind`(4) | 4 | 1 | measured / with_usage / with_tenant_config  -  the enablement headline is the gap between usage and tenant configuration |
| `gcinsight_ai_estate_tenant_objects` | I | `kind`(4) | 4 | 1 | TENANT-scoped skills / rules / automations / integrations. User-scoped objects are invisible to any identity but their owner and are not even countable, so this can never be a total |
| `gcinsight_carry_forward_age_seconds` | scan | `tier`(4) | 4 | 1 | age of the T3 state being carried. ALERT ON THIS  -  a stale carry-forward would otherwise republish last month's scores as current, indefinitely |
| `gcinsight_carry_forward_dropped_absent` | scan | `tier`(4) | 4 | 1 | series NOT republished because their stack has left the estate. The estate is re-discovered every run, so this going non-zero means a stack was decommissioned between the last T3 and this T1  -  expected, and the proof the golden rule holds |
| `gcinsight_carry_forward_series` | scan | `tier`(4) | 4 | 1 | PLAN 5.3  -  how many slower-tier series the hourly tier republished |
| `gcinsight_risk_org_members_staff_access` | E | `status`(4) | 4 | 1 | members by active / expired / none / unknown staff-access-window state. Identity and expiry timestamps remain in the S3 view, never labels |
| `gcinsight_scan_completed_timestamp_seconds` | scan | `tier`(4) | 4 | 1 | PLAN 1.8  -  alerting is on ITS AGE, not on exit code |
| `gcinsight_scan_coverage_ratio` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_duration_seconds` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_stacks_scannable` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_stacks_scanned` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_stacks_total` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_estate_feature_stacks` | A | `kind`(3) | 3 | 1 | incident / machine_learning / k6  -  provisioned capability nobody switched on. Emits 0 deliberately: a MEASURED zero is the finding here, unlike a structural zero elsewhere. Proves the feature is off, NOT that it is paid for |
| `gcinsight_estate_stacks` | A | `status`(3) | 3 | 1 |  |
| `gcinsight_estate_users_by_role` | A | `role`(3) | 3 | 1 |  |
| `gcinsight_ai_estate_investigations` | I | `kind`(2) | 2 | 1 | created by assistant vs by user. The INVENTORY is not collectable; these counts are |
| `gcinsight_dashboards_estate_anonymous_views` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_dashboards_viewed` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_datasources_queried` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_panels_queried` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_provisioned` | J | `version`(2) | 2 | 1 | dashboards PROVISIONED across the measured stacks, from inventory rather than from a usage-insights event. The denominator for the headline adoption share - the estate's whole dashboard count would divide by stacks this pillar never reached |
| `gcinsight_dashboards_estate_public` | J | `version`(2) | 2 | 1 | distinct public dashboards observed in use during the collection window |
| `gcinsight_dashboards_estate_public_events` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_queries_cached` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_queries_total` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_request_errors` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_requests` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_viewers` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_dashboards_estate_views` | J | `version`(2) | 2 | 1 |  |
| `gcinsight_estate_test_leftover_stacks` | A | `kind`(2) | 2 | 1 | idle vs billing  -  conflating them produced a bogus saving once already |
| `gcinsight_risk_service_accounts_total` | E | `kind`(2) | 2 | 1 | extsvc (auto-provisioned) vs custom |
| `gcinsight_ai_estate_category_combos` | I |  -  | 1 | 1 | how many category x surface combinations are in use. A drift detector: this rising is Assistant adding to its taxonomy, and it explains a series increase before somebody has to go looking for one |
| `gcinsight_ai_estate_messages_total` | I |  -  | 1 | 1 |  |
| `gcinsight_ai_estate_messages_uncategorised` | I |  -  | 1 | 1 | messages carrying no category. The honesty metric: no category chart may be normalised to total messages |
| `gcinsight_ai_estate_tokens` | I |  -  | 1 | 1 |  |
| `gcinsight_ai_estate_users` | I |  -  | 1 | 1 | sum of per-stack Assistant active users |
| `gcinsight_cost_adaptive_rules_applied_total` | B |  -  | 1 | 1 |  |
| `gcinsight_cost_adaptivelogs_pending_bytes_total` | B |  -  | 1 | 1 | bytes over the API's OWN UNSTATED window - never divide this into a rate. The endpoint ignores every window parameter and names no period |
| `gcinsight_cost_adaptivelogs_pending_bytes_unqueried` | B |  -  | 1 | 1 | the subset with no observed rule, query or dashboard references. It still needs an owner review before a drop rule is applied |
| `gcinsight_cost_adaptivelogs_pending_total` | B |  -  | 1 | 1 |  |
| `gcinsight_cost_adaptivelogs_recommendations_total` | B |  -  | 1 | 1 |  |
| `gcinsight_cost_adaptivelogs_stacks_measured` | B |  -  | 1 | 1 | denominator: stacks whose plugin proxy answered, so a coverage drop is visible |
| `gcinsight_cost_adaptivelogs_stacks_none_applied` | B |  -  | 1 | 1 | the headline: recommendations held and nothing acted on |
| `gcinsight_cost_adaptivelogs_stacks_with_recommendations` | B |  -  | 1 | 1 |  |
| `gcinsight_cost_billed_users` | B |  -  | 1 | 1 | estate total, no labels. Emitted by Pillar A today since it comes from the same inventory pass; the pillar attribution here is about which dashboard reads it |
| `gcinsight_cost_series_per_billed_user` | B |  -  | 1 | 1 | estate efficiency ratio; the per-stack version is a view column |
| `gcinsight_cost_stacks_without_adaptive` | B |  -  | 1 | 1 | stacks with active series but no applied Adaptive Metrics rules |
| `gcinsight_estate_active_users` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_alert_rules` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_daily_users` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_dashboards` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_us_region_stacks` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_version_drift_stacks` | A |  -  | 1 | 1 |  |
| `gcinsight_missing_credential_age_seconds` | I |  -  | 1 | 1 | age of the OLDEST individual gap, from emit/gapstate.py. THIS is the alert, at 48h. A `for` clause on the count never resets while stacks keep appearing, so it would fire having never seen one gap last two days. ABSENT when there is no gap |
| `gcinsight_risk_admin_heavy_stacks` | E |  -  | 1 | 1 | admin share above threshold |
| `gcinsight_risk_alert_routing_stacks_measured` | E |  -  | 1 | 1 | stacks whose alert-rule and contact-point provisioning endpoints both answered |
| `gcinsight_risk_alert_rules_active_inherited` | E |  -  | 1 | 1 | active rules with no direct receiver, therefore inheriting notification policy |
| `gcinsight_risk_alert_rules_active_missing_receiver` | E |  -  | 1 | 1 | active rules naming a receiver absent from the provisioning contact-point list |
| `gcinsight_risk_alert_rules_total` | E |  -  | 1 | 1 | rules across the measured alert-routing population |
| `gcinsight_risk_alert_rules_unverified_builtin` | E |  -  | 1 | 1 | rules naming grafana-default-email when that built-in is absent from provisioning; unverified, not called broken |
| `gcinsight_risk_collectors_active` | E |  -  | 1 | 1 | registrations NOT marked inactive, i.e. the real fleet. ABSENT rather than zero on a payload predating the split, because a 0 would say the estate runs no collectors |
| `gcinsight_risk_collectors_inactive` | E |  -  | 1 | 1 | registrations for collectors that are gone. Ephemeral compute churns these: the id embeds the hostname, so every pod reschedule creates one |
| `gcinsight_risk_collectors_total` | E |  -  | 1 | 1 | every REGISTRATION Fleet Management returns, unchanged so the series stays continuous. Read it with the active and inactive splits below |
| `gcinsight_risk_collectors_unconfigured` | E |  -  | 1 | 1 | alive, registered, and targeted by no ENABLED pipeline - so receiving no configuration. Also the matcher evaluator's sanity check |
| `gcinsight_risk_fleet_matchers_unparsed` | E |  -  | 1 | 1 | pipeline matchers this platform cannot parse. Non-zero means at least one 'collectors targeted' figure is UNKNOWN rather than small |
| `gcinsight_risk_org_members_admins` | E |  -  | 1 | 1 | Grafana.com org Admin membership count. Reported without a target or grade |
| `gcinsight_risk_org_members_viewers` | E |  -  | 1 | 1 | Grafana.com org Viewer membership count. Reported without a target or grade |
| `gcinsight_risk_pipelines_enabled` | E |  -  | 1 | 1 | a disabled pipeline still describes a target set but configures nothing; the plain pipeline count alone therefore overstates active configuration |
| `gcinsight_risk_pipelines_generated` | E |  -  | 1 | 1 | SOURCE_TYPE_GRAFANA. The rest were hand-authored, which is the difference between 'onboarding created this' and 'a team owns this' |
| `gcinsight_risk_pipelines_total` | E |  -  | 1 | 1 |  |
| `gcinsight_risk_plugin_drift_stacks` | E |  -  | 1 | 1 |  |
| `gcinsight_risk_public_dashboards_enabled` | E |  -  | 1 | 1 | the subset live right now. A disabled one is still a configured share, one click from live, so it counts towards the breach but not towards exposure |
| `gcinsight_risk_public_dashboards_enumerated` | E |  -  | 1 | 1 | public dashboards that EXIST across the measured stacks |
| `gcinsight_risk_public_dashboards_measured` | E |  -  | 1 | 1 | stacks the enumeration actually read. Never assume the rest are zero |
| `gcinsight_risk_public_dashboards_stacks` | E |  -  | 1 | 1 | how many stacks carry at least one - the number of owner conversations |
| `gcinsight_risk_public_dashboards_total` | E |  -  | 1 | 2 | RETIRED name, never emitted. Superseded twice: first by gcinsight_dashboards_estate_public (Pillar J, event-derived), then by the `_enumerated` family below, which counts the ones that EXIST. Kept declared so the decision stays on the record. PLAN 0.4, 18.17 |
| `gcinsight_risk_stacks_pipelines_no_collectors` | E |  -  | 1 | 1 | stacks with provisioned pipelines but no active collectors |
| `gcinsight_risk_stacks_without_delete_protection` | E |  -  | 1 | 1 | estate count, no labels  -  the per-stack risk detail is the view |
| `gcinsight_stacks_missing_credential` | I |  -  | 1 | 1 | count of provisionable stacks with no working credential. NOT the alert: a count above zero is normal for hours after the organisation creates a stack |
| `gcinsight_stacks_provisioned` | I |  -  | 1 | 1 |  |
| `gcinsight_usage_stickiness_ratio` | C |  -  | 1 | 1 | estate daily/active; per-stack is a view column |
| `gcinsight_value_savings_identified_currency` | F |  -  | 1 | 1 | the same reduction priced with the deployment's own rate card. ABSENT, never zero, when no rate card is supplied or no stack returned verbose counts |
| `gcinsight_value_savings_identified_series` | F |  -  | 1 | 1 | remediable series, summed from the per-metric reduction each Adaptive recommendation declares under ?verbose=true. Emitted whenever T3 data is present |
| `gcinsight_value_savings_unused_currency` | F |  -  | 1 | 1 | the unused-reference subset, priced. Same absence rule as above; still subject to owner review |
| `gcinsight_value_savings_unused_series` | F |  -  | 1 | 1 | the subset whose metrics appear in no observed rule, query or dashboard. It is a prioritisation signal, not permission to apply without owner review |
| `gcinsight_value_unit_cost_per_billed_user` | F |  -  | 1 | 1 |  |

## Deliberately views, not metrics

Each row is a decision: the data is per-stack detail a table panel renders from `views/`, and emitting it would cost the series in the third column for a trend nobody asked for.

| View | Pillar | Series if emitted | Phase | Why a view |
|---|---|---|---|---|
| `ai_assistant` | I | 271 | 1 | the wide per-stack table: users, days active, messages, categorised/uncategorised, tokens split chat vs investigation, tenant object counts, and why a stack was not measured |
| `ai_category_surface` | I | 5,691 | 1 | per-stack human-vs-machine detail; the bounded view avoids a stack-by-taxonomy metric cross product |
| `ai_config_disabled` | I | 1 | 1 | rules/automations/integrations that exist but are switched off. `enabled` is absent on skills, so only an explicit false counts  -  unknown is not disabled |
| `ai_credential_coverage` | I | 271 | 1 | which stacks lack a working reader credential, since when, and whether that is actionable  -  paused and opted-out stacks must read as skipped, not as failures |
| `ai_enablement_gap` | I | 1 | 1 | stacks with material Assistant use and no tenant configuration |
| `ai_mcp_auth_failed` | I | 1 | 1 | tenant MCP integrations whose last authentication failed |
| `ai_summary` | I | 1 | 1 |  |
| `ai_tenant_config` | I | 271 | 1 | one row per tenant skill/rule/automation/MCP integration: name, enabled, scope, createdBy, and `authenticationFailed` for MCPs. Bodies, rule content, MCP URLs and headers are NOT collected |
| `ai_token_outliers` | I | 1 | 1 |  |
| `cost_adaptive_metric_recommendations` | B | 1 | 1 | bounded top-ten-per-stack Adaptive Metrics action queue; metric names stay out of labels |
| `cost_cardinality_outliers` | B | 271 | 1 | point-in-time stack and label-name drill-down for cardinality outliers |
| `estate` | A | 271 | 1 | wide per-stack inventory: region, cluster, status, dashboards, alert rules, users by role, admin share, age, idle, drift, delete protection, leftover, created/updated by |
| `estate_leftovers_billing` | A | 1 | 1 | billing-active leftover candidates; row count is deployment-specific |
| `estate_leftovers_idle` | A | 1 | 1 | idle non-billing stack candidates; row count is deployment-specific |
| `insights_coverage` | J | 1 | 1 | the denominator: why a stack has no figures |
| `insights_dashboard_usage` | J | 1 | 1 | per-stack table |
| `insights_datasource_types` | J | 1 | 1 | which datasource types are actually QUERIED, not merely provisioned |
| `insights_public_dashboards` | J | 1 | 1 | observed activity list: stack, dashboard, publicDashboardUid, events |
| `insights_summary` | J | 1 | 1 |  |
| `insights_top_dashboards` | J | 1 | 1 |  |
| `maturity_dimensions` | D | 2,439 | 1 | a table shows every dimension's contribution; only the composite needs trending |
| `public_dashboard_inventory` | E | 271 | 3 | complete configured public-dashboard inventory for comparison with local policy |
| `risk_admin_share_per_stack` | E | 271 | 1 |  |
| `risk_alert_routing` | E | 1 | 1 | per-stack rule routing and contact-point coverage; point-in-time inventory |
| `risk_alert_routing_findings` | E | 1 | 1 | bounded named rule drill-down; rule identity stays out of metric labels |
| `risk_fleet_attributes` | E | 1 | 1 | bounded active-collector version, OS, platform, source and type breakdowns |
| `risk_fleet_pipelines` | E | 1 | 1 | named pipeline matcher reach; full Alloy contents are never retained |
| `risk_org_members` | E | 1 | 1 | clear-PII named org membership and staff-access-window drill-down |
| `risk_plugin_version_drift` | E | 271 | 1 |  |
| `risk_sa_and_token_inventory` | E | 271 | 1 | named service-account and token inventory stays out of metric labels |
| `usage_query_cost_attribution` | C | 271 | 2 |  |

## Rules this table enforces

- A per-stack metric carries **at most one** other label, and its enum is **≤ 4**. `stack` x `kind`(10) is 2,710 series  -  that is a table.
- A per-stack time series must carry a bounded, actionable trend. Identity-bearing or wide cross-product detail belongs in a view, even under the relaxed total ceiling.
- Label keys must be in `collector/emit/guard.py`'s allow-list. The guard is the runtime gate; this is the design-time one.

