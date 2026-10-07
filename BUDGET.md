# Series budget

**Generated from `collector/emit/budget.py`  -  do not hand-edit.**
Regenerate: `python3 -m collector.emit.budget > BUDGET.md`

## Declared capacity

| | Series |
|---|---:|
| **Declared (all phases)** | **13,811** |
| Phase 1 only | 13,811 |
| Runaway ceiling | 100,000 |

Everything lands on the configured write stack alone. Compare the measured platform footprint with that stack's own series over the same range; the org total is never the denominator. The 100,000 ceiling is a runaway backstop, not a target and not a licence for unbounded labels.

**This table is declared capacity, not the measured footprint  -  do not quote it as live use.** Declared capacity reserves every bounded enum at its ceiling and therefore exceeds the series present at a particular instant. Re-measure with a range query and a matching denominator before reporting footprint; never copy a measured count into this generated document.

## By pillar

| Pillar | Mimir series |
|---|---|
| A | 296 |
| B | 1,101 |
| C | 14 |
| D | 582 |
| E | 1,125 |
| F | 21 |
| I | 895 |
| J | 4,400 |
| K | 973 |
| L | 4,066 |
| scan | 338 |
| **Total** | **13,811** |

## Metrics

| Metric | Pillar | Labels | Series | Phase | Note |
|---|---|---|---|---|---|
| `gcinsight_labelling_rules_evaluated` | L | `stack`(271), `signal`(4) | 1,084 | 1 | pass/fail rule counts where evidence was evaluated; missing input is absent |
| `gcinsight_labelling_rules_passed` | L | `stack`(271), `signal`(4) | 1,084 | 1 | passed rules over the same evaluated population; no cross-signal metric |
| `gcinsight_labelling_score` | L | `stack`(271), `signal`(4) | 1,084 | 1 | fixed-weight 0-100 score, only at coverage >=0.8; compare within catalogue version |
| `gcinsight_labelling_findings` | L | `stack`(271), `severity`(3) | 813 | 1 | observed failed rules by severity; absent below severity coverage floor. Escalatable rules remain in every affected severity denominator |
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
| `gcinsight_stack_label_cardinality_findings` | E | `stack`(271), `kind`(2) | 542 | 1 | per-stack counts split into high-confidence and possible. Label names remain in S3 and Loki and never become metric labels |
| `gcinsight_ai_machine_share` | I | `stack`(271) | 271 | 1 | share of CATEGORISED messages from a non-web surface (cli/a2a/automation/lodestone/slack). Absent where nothing was categorised. Exists in no other datasource |
| `gcinsight_ai_messages` | I | `stack`(271) | 271 | 1 | Assistant user messages in the 30-day window. Emitted for every stack whose Assistant API was READ, zeros included, so an absent series still means 'not measured' and never 'not used' |
| `gcinsight_ai_tokens_per_active_user` | I | `stack`(271) | 271 | 1 | the outlier detector. ABSENT where there are no active users: the ratio is undefined, and a zero would rank a dormant stack as the most efficient |
| `gcinsight_cost_adaptivelogs_pending_bytes` | B | `stack`(271) | 271 | 1 | per stack, only where recommendations exist; the view carries the breakdown |
| `gcinsight_coverage_stack_clusters` | K | `stack`(271) | 271 | 1 | distinct explicitly-windowed Mimir cluster label values |
| `gcinsight_coverage_stack_services` | K | `stack`(271) | 271 | 1 | application population from the canonical service_name union; full discovered count before the view's top-N bound |
| `gcinsight_coverage_stack_technologies` | K | `stack`(271) | 271 | 1 | technologies present through versioned sentinel matching |
| `gcinsight_stack_active_series` | A | `stack`(271) | 271 | 1 | the metrics cost driver; growth per stack is the platform team's core question |
| `gcinsight_stack_billed_users` | B | `stack`(271) | 271 | 1 | billingActiveUsers, NEVER currentActiveUsers. Named `stack_` not `cost_` so it cannot collide with the estate rollup of the same quantity |
| `gcinsight_stack_collectors_active` | E | `stack`(271) | 271 | 1 | the per-stack half; use it to find registration concentration and churn |
| `gcinsight_stack_fleet_fast_scrape_pipelines` | E | `stack`(271) | 271 | 1 | enabled, reaching Fleet pipelines scraping faster than the default interval. Per stack because the alert names the stack and remediation is a trend; ABSENT where Fleet was not read or the payload predates the interval parser |
| `gcinsight_input_age_seconds` | scan | `tier`(4), `input`(30) | 120 | 1 | age of the input the figures were computed from  -  NOT of the tier that ran. This is what the per-dashboard freshness panels read; the old single 'Data age' showed T1's timestamp on all eight dashboards and so claimed hourly freshness for 6-hourly data. ABSENT rather than 0 when the input is unavailable: a 0 would read as 'just gathered' |
| `gcinsight_input_available` | scan | `tier`(4), `input`(30) | 120 | 1 | 1/0 per consumed input. 0 means the dependent views were WITHHELD this run |
| `gcinsight_ai_estate_messages` | I | `category`(8), `surface`(8) | 64 | 1 | fixed category/surface projections plus other, summed after projection; NO `stack` label. Original per-stack names remain in `ai_category_surface` |
| `gcinsight_coverage_technology_stacks` | K | `kind`(63) | 63 | 1 | one bounded registry enum per technology; value is measured stacks present |
| `gcinsight_coverage_unscored` | K | `component`(8), `reason`(7) | 56 | 1 | bounded component/reason counts; product absence and unavailable evidence are excluded from the score rather than published as failed coverage |
| `gcinsight_scan_stacks_failed` | scan | `tier`(4), `reason`(8) | 32 | 1 | fixed publication projection plus other; 8-slot capacity is not an exception taxonomy |
| `gcinsight_findings` | scan | `kind`(18) | 18 | 1 | count per finding kind, derived from the pillar views by pillars/findings.py. A kind the running tier cannot compute is ABSENT, never 0 |
| `gcinsight_maturity_dimension_mean` | D | `dimension`(9), `version`(2) | 18 | 1 | estate mean per rubric dimension  -  answers 'which dimension is the estate weakest on', which the per-stack view cannot trend without a stack-by-dimension cross product. Mean is over the stacks that SCORED that dimension, excluding the four unscored reasons |
| `gcinsight_dashboards_estate_surface_requests` | J | `surface`(8), `version`(2) | 16 | 1 | daily query-request trend by the closed Grafana surface enum; point-in-time per-stack detail stays in insights_surface_usage |
| `gcinsight_dashboards_estate_surface_stacks` | J | `surface`(8), `version`(2) | 16 | 1 | daily count of measured stacks with at least one request through each observed surface |
| `gcinsight_coverage_capability_gap` | K | `kind`(14) | 14 | 1 | fixed capability enum; four additional estate-only observation gaps track SM, Kubernetes, Knowledge Graph and PDC outreach closure with no stack multiplier. Reporting populations exclude missing observations; unknown populations emit nothing, measured zero gaps remain findings, not human adoption |
| `gcinsight_scan_stacks_skipped` | scan | `tier`(4), `reason`(3) | 12 | 1 | runtime reasons paused / unavailable, with a source-backed tier/reason relation |
| `gcinsight_value_benchmark` | F | `kind`(10) | 10 | 1 | per-stack discrete median (upper-middle for even populations); p90/worst and current population counts are in value_benchmarks, not this metric |
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
| `gcinsight_coverage_services_by_depth` | K | `kind`(4) | 4 | 1 | service assets carrying exactly 1, 2, 3 or 4 canonical signals |
| `gcinsight_coverage_services_by_signal` | K | `kind`(4) | 4 | 1 | service assets carrying canonical metrics, logs, traces or profiles identity |
| `gcinsight_coverage_stacks_by_technology_count` | K | `kind`(4) | 4 | 1 | measured stacks detecting 0, 1, 2-4 or 5+ registry technologies |
| `gcinsight_risk_org_members_staff_access` | E | `status`(4) | 4 | 1 | members by active / expired / none / unknown staff-access-window state. Identity and expiry timestamps remain in the S3 view, never labels |
| `gcinsight_scan_completed_timestamp_seconds` | scan | `tier`(4) | 4 | 1 | PLAN 1.8  -  alerting is on ITS AGE, not on exit code |
| `gcinsight_scan_coverage_ratio` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_duration_seconds` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_stacks_scannable` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_stacks_scanned` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_scan_stacks_total` | scan | `tier`(4) | 4 | 1 |  |
| `gcinsight_coverage_service_identity` | K | `kind`(3) | 3 | 1 | canonical, legacy-only and overlap counts; generic service is never silently promoted to service_name |
| `gcinsight_coverage_service_population` | K | `kind`(3) | 3 | 1 | application, platform and infrastructure-unit populations; every discovered identity is counted exactly once |
| `gcinsight_estate_feature_stacks` | A | `kind`(3) | 3 | 1 | incident / machine_learning / k6  -  provisioned capability nobody switched on. Emits 0 deliberately: a MEASURED zero is the finding here, unlike a structural zero elsewhere. Proves the feature is off, NOT that it is paid for |
| `gcinsight_estate_stacks` | A | `status`(3) | 3 | 1 |  |
| `gcinsight_estate_users_by_role` | A | `role`(3) | 3 | 1 |  |
| `gcinsight_risk_retention_change_requests` | E | `status`(3) | 3 | 1 | self-serve requests by applied, pending or rejected; identity stays in the view |
| `gcinsight_ai_estate_investigations` | I | `kind`(2) | 2 | 1 | created by assistant vs by user. The INVENTORY is not collectable; these counts are |
| `gcinsight_coverage_instrumentation_stacks` | K | `kind`(2) | 2 | 1 | official SDK and deduplicated SDK-equivalent stack counts; protocol adoption stays live on grafanacloud-usage |
| `gcinsight_coverage_metric_names` | K | `kind`(2) | 2 | 1 | matched vs unmatched metric-name evidence; unmatched is a registry backlog, never a coverage share |
| `gcinsight_coverage_service_applicable_components_mean` | K | `version`(2) | 2 | 1 | mean score denominator over exactly the same services as completeness |
| `gcinsight_coverage_service_completeness_mean` | K | `version`(2) | 2 | 1 | mean over non-ephemeral services with at least four applicable components |
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
| `gcinsight_ai_estate_category_combos` | I |  -  | 1 | 1 | unprojected category x surface combination count; upstream drift remains visible even when new names collapse into other rather than creating metric series |
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
| `gcinsight_coverage_stacks_measured` | K |  -  | 1 | 1 | stacks whose atomic four-signal inventory succeeded |
| `gcinsight_estate_active_users` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_alert_rules` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_daily_users` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_dashboards` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_us_region_stacks` | A |  -  | 1 | 1 |  |
| `gcinsight_estate_version_drift_stacks` | A |  -  | 1 | 1 |  |
| `gcinsight_labelling_catalogue_version` | L |  -  | 1 | 1 | estate-level numeric catalogue version, no version label |
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
| `gcinsight_risk_fleet_fast_scrape_stacks` | E |  -  | 1 | 1 | stacks with at least one faster-than-default Fleet pipeline |
| `gcinsight_risk_fleet_matchers_unparsed` | E |  -  | 1 | 1 | pipeline matchers this platform cannot parse. Non-zero means at least one 'collectors targeted' figure is UNKNOWN rather than small |
| `gcinsight_risk_fleet_scrape_interval_default_seconds` | E |  -  | 1 | 1 | the deployment's configured default, so panels and readers compare against the same number the collector used |
| `gcinsight_risk_fleet_scrape_intervals_unparsed` | E |  -  | 1 | 1 | interval expressions that are not literals (arguments, env lookups). Non-zero means at least one pipeline's cadence is UNKNOWN rather than default |
| `gcinsight_risk_label_cardinality_stacks_measured` | E |  -  | 1 | 1 | stacks whose Mimir top-cardinality label-name response was readable |
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
| `gcinsight_risk_retention_change_request_stacks` | E |  -  | 1 | 1 | stacks whose Databases Configuration request queue was readable |
| `gcinsight_risk_retention_policy_compliant_stacks` | E |  -  | 1 | 1 | stacks satisfying every configured selector expectation; absent without a readable policy measurement |
| `gcinsight_risk_retention_policy_gap_stacks` | E |  -  | 1 | 1 | confirmed breaches among readable stacks; unreadable stacks are counted separately |
| `gcinsight_risk_retention_policy_unreadable_stacks` | E |  -  | 1 | 1 | live stacks with unreadable Loki limits or ambiguous selector overlap |
| `gcinsight_risk_retention_stacks_measured` | E |  -  | 1 | 1 | stacks whose effective Loki limits response was readable |
| `gcinsight_risk_stacks_pipelines_no_collectors` | E |  -  | 1 | 1 | stacks with provisioned pipelines but no active collectors |
| `gcinsight_risk_stacks_without_delete_protection` | E |  -  | 1 | 1 | estate count, no labels  -  the per-stack risk detail is the view |
| `gcinsight_stacks_missing_credential` | I |  -  | 1 | 1 | count of provisionable stacks with no working credential. NOT the alert: a count above zero is normal for hours after the organisation creates a stack |
| `gcinsight_stacks_provisioned` | I |  -  | 1 | 1 |  |
| `gcinsight_usage_datasource_types_distinct` | C |  -  | 1 | 1 | distinct provisioned datasource types estate-wide; vendor names stay in S3 and the auto-provisioned knowledge-graph datasource is excluded |
| `gcinsight_usage_stickiness_ratio` | C |  -  | 1 | 1 | estate daily/active; per-stack is a view column |
| `gcinsight_usage_synthetic_monitoring_datasource_stacks` | C |  -  | 1 | 1 | fixed scalar preserving the provisioned-versus-active Synthetic Monitoring comparison without a datasource-type label |
| `gcinsight_value_savings_identified_currency` | F |  -  | 1 | 1 | the same reduction priced with the deployment's own rate card. ABSENT, never zero, when no rate card is supplied or no stack returned verbose counts |
| `gcinsight_value_savings_identified_series` | F |  -  | 1 | 1 | remediable series, summed from the per-metric reduction each Adaptive recommendation declares under ?verbose=true. Emitted whenever T3 data is present |
| `gcinsight_value_savings_unused_currency` | F |  -  | 1 | 1 | the unused-reference subset, priced. Same absence rule as above; still subject to owner review |
| `gcinsight_value_savings_unused_series` | F |  -  | 1 | 1 | the subset whose metrics appear in no observed rule, query or dashboard. It is a prioritisation signal, not permission to apply without owner review |
| `gcinsight_value_unit_cost_per_billed_user` | F |  -  | 1 | 1 |  |

## Deliberately views, not metrics

Each row is a decision: the data is per-stack detail a table panel renders from `views/`, and emitting it would cost the series in the third column for a trend nobody asked for.

| View | Pillar | Series if emitted | Phase | Why a view |
|---|---|---|---|---|
| `ai_agent_observability` | I | 1 | 1 | live-stack 30d maximum generation rate reporting, independently available from Assistant plugin inputs; absent stays unknown, not cumulative volume or entitlement |
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
| `coverage_capability_adoption` | K | 10 | 1 | population, used and opportunity counts with the denominator basis and next step |
| `coverage_capability_opportunities` | K | 2,710 | 1 | named call list ranked by active series; stack identity never becomes a new metric |
| `coverage_cluster_register` | K | 271 | 1 | named observed clusters; names never become labels |
| `coverage_legacy_service_register` | K | 271 | 1 | generic Mimir service values retained separately as legacy identity evidence |
| `coverage_metric_name_register` | K | 271 | 1 | metric names and their registry classification; names never become labels |
| `coverage_producing_signals` | A | 1 | 1 | documented Metrics and Traces backend production over the prior 24 hours |
| `coverage_service_register` | K | 271 | 1 | top-N named services with signal depth and explicit alert/dashboard metadata |
| `coverage_summary` | K | 271 | 1 | per-stack counts, registry version, truncation and unmatched-name backlog |
| `coverage_technology_register` | K | 17,073 | 1 | stack x technology is current-state identity detail, not a time series |
| `estate` | A | 271 | 1 | wide per-stack inventory: region, cluster, status, dashboards, alert rules, users by role, admin share, age, idle, drift, delete protection, leftover, created/updated by |
| `estate_leftovers_billing` | A | 1 | 1 | billing-active leftover candidates; row count is deployment-specific |
| `estate_leftovers_idle` | A | 1 | 1 | idle non-billing stack candidates; row count is deployment-specific |
| `insights_coverage` | J | 1 | 1 | the denominator: why a stack has no figures |
| `insights_dashboard_usage` | J | 1 | 1 | per-stack table |
| `insights_datasource_types` | J | 1 | 1 | which datasource types are actually QUERIED, not merely provisioned |
| `insights_public_dashboards` | J | 1 | 1 | observed activity list: stack, dashboard, publicDashboardUid, events |
| `insights_query_mix` | J | 1 | 1 | top 20 datasource types and panel plugins per stack, plus one remainder row |
| `insights_summary` | J | 1 | 1 |  |
| `insights_surface_unmapped` | J | 1 | 1 | top unmapped raw `source` values per stack; raw values never become metric labels |
| `insights_surface_usage` | J | 1 | 1 | per-stack query requests, share and distinct users by closed surface enum |
| `insights_surface_usage_estate` | J | 1 | 1 | estate query requests, stacks queried and sum of per-stack distinct users by surface |
| `insights_top_dashboards` | J | 1 | 1 |  |
| `labelling_cross_signal` | L | 271 | 1 | service-set sizes and differences plus metric cluster count; sets stay transient |
| `labelling_findings` | L | 271 | 1 | S3-only rule results and numeric/enum evidence, never FindingSpec/events |
| `labelling_label_register` | L | 271 | 1 | S3-only minimized names/class/counts, capped at 256 whole rows per stack/signal; no raw values or PII shape counts |
| `labelling_stack_summary` | L | 271 | 1 | per-signal score with weighted coverage, severity coverage and catalogue version |
| `library_panels_inventory` | C | 1 | 1 | default-off configured library panel counts after same-token wildcard folder coverage; zero product series, one input adds eight planned existing provenance series across four tiers; not usage, rendered instances or panel details |
| `maturity_dimensions` | D | 2,439 | 1 | a table shows every dimension's contribution; only the composite needs trending |
| `public_dashboard_inventory` | E | 271 | 3 | complete configured public-dashboard inventory for comparison with local policy |
| `risk_admin_share_per_stack` | E | 271 | 1 |  |
| `risk_alert_routing` | E | 1 | 1 | per-stack rule routing and contact-point coverage; point-in-time inventory |
| `risk_alert_routing_findings` | E | 1 | 1 | bounded named rule drill-down; rule identity stays out of metric labels |
| `risk_fleet_attributes` | E | 1 | 1 | bounded active-collector version, OS, platform, source and type breakdowns |
| `risk_fleet_pipelines` | E | 1 | 1 | named pipeline matcher reach; full Alloy contents are never retained |
| `risk_fleet_scrape_intervals` | E | 1 | 1 | named pipelines whose declared scrape intervals differ from the default; parsed in memory, contents never retained |
| `risk_label_cardinality` | E | 271 | 1 | Mimir top-cardinality label names and counts. Identity-bearing label names stay in S3 and Loki, never metric labels |
| `risk_org_members` | E | 1 | 1 | clear-PII named org membership and staff-access-window drill-down |
| `risk_plugin_version_drift` | E | 271 | 1 |  |
| `risk_retention_change_requests` | E | 1 | 1 | self-serve request record; author and message never become metric labels |
| `risk_retention_policy_gaps` | E | 1 | 1 | deployment-supplied selector expectations not met by readable effective limits |
| `risk_retention_policy_status` | E | 1 | 1 | each live stack and configured selector expectation classified as compliant, below policy or unreadable |
| `risk_retention_stream` | E | 1 | 1 | effective per-stream periods and selectors from Loki tenant limits |
| `risk_sa_and_token_inventory` | E | 271 | 1 | named service-account and token inventory stays out of metric labels |
| `usage_datasource_inventory` | C | 271 | 1 | live-inventory stack, vendor datasource type and instance count; type names stay out of metric labels |
| `usage_enterprise_catalogue` | C | 1 | 1 | configured datasource rollup qualified by measured inventory/catalogue coverage; current public Enterprise status, never installed licence or activity |
| `usage_query_cost_attribution` | C | 271 | 2 |  |

## Runtime label contracts

Runtime vocabularies below come from producer/source contracts, not capacity integers or fixture observations. Stack and region remain fresh-inventory discovery domains. Spare capacity has no extra supported value; current versions are not numerical capacities. These offline coverage/conformance helpers are NOT publisher enforcement. The Assistant category/surface and scan-failure reason projections are separately enforced in producers and scan's common publication boundary. Their fixed output contracts do not make upstream strings or runtime exception classes exhaustive enums.

| Metric | Label | Class | Runtime values | Capacity | Spare capacity / limitation | Witness |
|---|---|---|---|---|---|---|
| `gcinsight_adaptive_recommendations` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_adaptive_recommendations` | `status` | fixed | `pending`, `applied` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.cost.build literal status sites |
| `gcinsight_ai_estate_investigations` | `kind` | fixed | `assistant`, `user` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.ai.INVESTIGATION_ORIGINS -> build |
| `gcinsight_ai_estate_messages` | `category` | fixed | `Investigate`, `Observe`, `Dashboard`, `Learn`, `Other`, `Errors`, `other` | 8 | 1 unnamed slot(s). Projection only; upstream strings remain open/UNKNOWN. Spare capacity is unnamed, not an accepted input. | sources.assistant metric projection -> pillars.ai.build; scan.project_metric_domains before carry storage and remote_write |
| `gcinsight_ai_estate_messages` | `surface` | fixed | `web`, `cli`, `a2a`, `automation`, `slack`, `lodestone`, `unknown`, `other` | 8 | 0 unnamed slot(s). Projection only; upstream strings remain open/UNKNOWN. Spare capacity is unnamed, not an accepted input. | sources.assistant metric projection -> pillars.ai.build; scan.project_metric_domains before carry storage and remote_write |
| `gcinsight_ai_estate_stacks` | `kind` | fixed | `measured`, `with_usage`, `with_tenant_config` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.ai.build literal kind sites |
| `gcinsight_ai_estate_tenant_objects` | `kind` | fixed | `skills`, `rules`, `automations`, `integrations` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.ai.TENANT_KINDS -> build |
| `gcinsight_ai_machine_share` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_ai_messages` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_ai_tokens_per_active_user` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_carry_forward_age_seconds` | `tier` | fixed | `t1` | 4 | 3 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_carry_forward_dropped_absent` | `tier` | fixed | `t1` | 4 | 3 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_carry_forward_series` | `tier` | fixed | `t1` | 4 | 3 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_cost_adaptivelogs_pending_bytes` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_cost_usage_by_signal` | `signal` | fixed | `metrics`, `logs`, `traces`, `profiles`, `graphite` | 6 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.cost.SIGNAL_USAGE -> build emission loop |
| `gcinsight_coverage_capability_gap` | `kind` | fixed | `profiles`, `slos`, `traces`, `span_metrics`, `service_graphs`, `native_histograms`, `exemplars`, `irm_oncall`, `k6`, `frontend_observability`, `synthetic_monitoring`, `kubernetes`, `knowledge_graph`, `pdc` | 14 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.ADOPTION_CAPABILITIES -> _adoption_surface |
| `gcinsight_coverage_instrumentation_stacks` | `kind` | fixed | `sdk`, `sdk_equivalent` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build instrumentation_stacks -> emission |
| `gcinsight_coverage_metric_names` | `kind` | fixed | `matched`, `unmatched` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build classified_counts -> emission |
| `gcinsight_coverage_service_applicable_components_mean` | `version` | fixed | `4` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | observability_score.VERSION -> pillars.coverage.build |
| `gcinsight_coverage_service_completeness_mean` | `version` | fixed | `4` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | observability_score.VERSION -> pillars.coverage.build |
| `gcinsight_coverage_service_identity` | `kind` | fixed | `canonical`, `legacy_only`, `overlap` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build identity_counts -> emission |
| `gcinsight_coverage_service_population` | `kind` | fixed | `application`, `platform`, `infrastructure_unit` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build population_counts -> emission |
| `gcinsight_coverage_services_by_depth` | `kind` | fixed | `1`, `2`, `3`, `4` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build depth_counts range(1,5) -> emission |
| `gcinsight_coverage_services_by_signal` | `kind` | fixed | `metrics`, `logs`, `traces`, `profiles` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build signal_counts -> emission |
| `gcinsight_coverage_stack_clusters` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_coverage_stack_services` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_coverage_stack_technologies` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_coverage_stacks_by_technology_count` | `kind` | fixed | `0`, `1`, `2-4`, `5+` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.build technology_count_distribution -> emission |
| `gcinsight_coverage_technology_stacks` | `kind` | fixed | `airflow`, `akuity`, `alloy`, `alloy_ebpf_profiling`, `argocd`, `asserts`, `aws_cloudwatch`, `beyla_ebpf`, `cadvisor`, `cert_manager`, `clickhouse`, `cloudnativepg`, `cockroachdb`, `controller_runtime`, `coredns`, `crossplane`, `elasticsearch`, `envoy`, `etcd`, `external_dns`, `frontend_observability`, `gcp_stackdriver`, `github_actions`, `github_apps`, `gitlab_runner`, `hikaricp`, `jvm_micrometer`, `k6_health_check`, `kafka_client`, `karpenter`, `kubelet`, `kubernetes`, `linux`, `logback`, `mongodb`, `mssql`, `mysql`, `nomad`, `nvidia_dcgm`, `open_ondemand`, `opencost`, `otel_collector`, `otel_db_client`, `otel_hostmetrics`, `otel_http`, `otel_sdk`, `postgresql`, `probe_checks`, `prometheus`, `rabbitmq`, `redis`, `slurm`, `spring_boot`, `synthetic_monitoring`, `tempo_service_graph`, `tempo_span_metrics`, `temporal`, `tomcat`, `traefik`, `vault`, `victoriametrics`, `weka`, `windows_exporter` | 63 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | technology_registry.REGISTRY.entries -> pillars.coverage.build |
| `gcinsight_coverage_unscored` | `component` | fixed | `alert`, `dashboard`, `profiles`, `row`, `slo` | 8 | 3 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.UNSCORED_PAIRS -> exact pair emission loop |
| `gcinsight_coverage_unscored` | `reason` | fixed | `ephemeral_identity`, `evidence_unavailable`, `infrastructure_identity`, `inventory_unavailable`, `platform_identity`, `product_not_in_use`, `signal_not_in_use` | 7 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.coverage.UNSCORED_PAIRS -> exact pair emission loop |
| `gcinsight_dashboards_anonymous_views` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_anonymous_views` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_cache_hit_ratio` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_cache_hit_ratio` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_anonymous_views` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_dashboards_viewed` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_datasources_queried` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_panels_queried` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_provisioned` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_public` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_public_events` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_queries_cached` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_queries_total` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_request_errors` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_requests` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_stacks` | `kind` | fixed | `measured`, `with_views`, `with_public_dashboards` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.insights.build literal kind sites |
| `gcinsight_dashboards_estate_stacks` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_surface_requests` | `surface` | fixed | `dashboard`, `explore`, `app_scenes`, `assistant`, `app`, `kubernetes`, `unknown`, `other` | 8 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | sources.usage_insights.SURFACE_VALUES -> pillars.insights.build |
| `gcinsight_dashboards_estate_surface_requests` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_surface_stacks` | `surface` | fixed | `dashboard`, `explore`, `app_scenes`, `assistant`, `app`, `kubernetes`, `unknown`, `other` | 8 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | sources.usage_insights.SURFACE_VALUES -> pillars.insights.build |
| `gcinsight_dashboards_estate_surface_stacks` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_viewers` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_estate_views` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_panel_queries` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_panel_queries` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_public_events` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_public_events` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_query_errors` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_query_errors` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_viewed` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_viewed` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_viewers` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_viewers` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_dashboards_views` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_dashboards_views` | `version` | fixed | `2` | 2 | 1 unnamed slot(s). Contaminated prior history is unversioned, not version=1. | pillars.insights.METRIC_EPOCH -> final build output seam |
| `gcinsight_estate_feature_stacks` | `kind` | fixed | `incident`, `machine_learning`, `k6` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.estate.build kind/enabled loop |
| `gcinsight_estate_stacks` | `status` | fixed | `total`, `active`, `paused` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.estate.build literal status sites |
| `gcinsight_estate_stacks_by_region` | `region` | discovered | Not enumerated | 8 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory pillars.estate.build regionSlug union, with unknown fallback |
| `gcinsight_estate_test_leftover_stacks` | `kind` | fixed | `idle`, `billing` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.estate.build literal leftover sites |
| `gcinsight_estate_users_by_role` | `role` | fixed | `admin`, `editor`, `viewer` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.estate.build role/field loop |
| `gcinsight_findings` | `kind` | fixed | `cardinality_outlier`, `adaptive_headroom`, `admin_sprawl`, `label_cardinality_high_confidence`, `label_cardinality_possible`, `service_account_risk`, `no_delete_protection`, `fleet_dead_collector`, `fleet_fast_scrape`, `plugin_drift`, `leftover_stack_billing`, `leftover_stack_idle`, `version_drift`, `dormant_stack`, `mcp_auth_failed`, `assistant_no_tenant_config`, `assistant_token_outlier`, `assistant_config_disabled` | 18 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.findings.SPECS -> derive -> metrics |
| `gcinsight_input_age_seconds` | `input` | fixed | `access_policies`, `org_members`, `stack_detail`, `service_accounts`, `dataplane`, `assistant`, `insights`, `fleet`, `adaptive_logs`, `adaptive_traces`, `public_dashboards`, `alert_routing`, `dashboard_inventory`, `datasource_query_cost`, `signal_inventory`, `capability_adoption`, `loki_config`, `slo_inventory`, `synthetic_inventory`, `irm_integrations`, `irm_alert_groups`, `faro_apps`, `ml_jobs`, `cloud_accounts`, `pdc_networks`, `reports_inventory`, `playlists_inventory`, `library_panels_inventory`, `label_risk`, `label_inventory` | 30 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | emit.hydrate.INPUT_OWNER -> hydrate -> report_metrics |
| `gcinsight_input_age_seconds` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_input_available` | `input` | fixed | `access_policies`, `org_members`, `stack_detail`, `service_accounts`, `dataplane`, `assistant`, `insights`, `fleet`, `adaptive_logs`, `adaptive_traces`, `public_dashboards`, `alert_routing`, `dashboard_inventory`, `datasource_query_cost`, `signal_inventory`, `capability_adoption`, `loki_config`, `slo_inventory`, `synthetic_inventory`, `irm_integrations`, `irm_alert_groups`, `faro_apps`, `ml_jobs`, `cloud_accounts`, `pdc_networks`, `reports_inventory`, `playlists_inventory`, `library_panels_inventory`, `label_risk`, `label_inventory` | 30 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | emit.hydrate.INPUT_OWNER -> hydrate -> report_metrics |
| `gcinsight_input_available` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_labelling_findings` | `severity` | fixed | `low`, `medium`, `high` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.labelling.SEVERITIES -> build |
| `gcinsight_labelling_findings` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_labelling_rules_evaluated` | `signal` | fixed | `metrics`, `logs`, `traces`, `profiles` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.labelling.SIGNALS -> build |
| `gcinsight_labelling_rules_evaluated` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_labelling_rules_passed` | `signal` | fixed | `metrics`, `logs`, `traces`, `profiles` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.labelling.SIGNALS -> build |
| `gcinsight_labelling_rules_passed` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_labelling_score` | `signal` | fixed | `metrics`, `logs`, `traces`, `profiles` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.labelling.SIGNALS -> build |
| `gcinsight_labelling_score` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_maturity_dimension_mean` | `dimension` | fixed | `signal_breadth`, `alerting_proportionality`, `adaptive_adoption`, `engagement`, `access_hygiene`, `cardinality_discipline`, `dashboard_utilisation`, `datasource_breadth`, `collector_health` | 9 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.maturity.RUBRIC -> dimension_means -> build |
| `gcinsight_maturity_dimension_mean` | `version` | fixed | `1` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | pillars.maturity.RUBRIC_VERSION -> build |
| `gcinsight_maturity_percentile` | `kind` | fixed | `median`, `p90`, `worst` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.maturity.build percentile literal sites |
| `gcinsight_maturity_percentile` | `version` | fixed | `1` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | pillars.maturity.RUBRIC_VERSION -> build |
| `gcinsight_maturity_score` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_maturity_score` | `version` | fixed | `1` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | pillars.maturity.RUBRIC_VERSION -> build |
| `gcinsight_maturity_stacks_by_tier` | `kind` | fixed | `leading`, `solid`, `lagging`, `dormant` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.maturity.TIERS -> build |
| `gcinsight_maturity_stacks_by_tier` | `version` | fixed | `1` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | pillars.maturity.RUBRIC_VERSION -> build |
| `gcinsight_maturity_unscored` | `reason` | fixed | `paused`, `too_few_users`, `no_signal_above_floor`, `insufficient_rubric_coverage` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.maturity.UNSCORED_REASONS -> build |
| `gcinsight_maturity_unscored` | `version` | fixed | `1` | 2 | 1 unnamed slot(s). Transition capacity is unnamed; no historical/future version is invented. | pillars.maturity.RUBRIC_VERSION -> build |
| `gcinsight_risk_org_members_staff_access` | `status` | fixed | `active`, `expired`, `none`, `unknown` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.risk.ORG_MEMBER_STAFF_ACCESS_STATES -> build |
| `gcinsight_risk_retention_change_requests` | `status` | fixed | `applied`, `pending`, `rejected` | 3 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.retention.REQUEST_STATUSES -> build |
| `gcinsight_risk_service_accounts_total` | `kind` | fixed | `extsvc`, `custom` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | sources.serviceaccounts.record -> pillars.risk.build |
| `gcinsight_scan_completed_timestamp_seconds` | `tier` | fixed | `t1`, `t2`, `t3`, `t4` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_coverage_ratio` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_duration_seconds` | `tier` | fixed | `t1`, `t2`, `t3`, `t4` | 4 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_stacks_failed` | `reason` | fixed | `RuntimeError`, `KeyError`, `ValueError`, `MethodNotAllowed`, `JSONDecodeError`, `DeadlineExceeded`, `other` | 8 | 1 unnamed slot(s). Projection only; residual exception taxonomy remains UNKNOWN. Spare capacity is unnamed. | gcom/dataplane exception accounting -> scan.ScanCoverage.as_metrics; scan.project_metric_domains before carry storage and remote_write |
| `gcinsight_scan_stacks_failed` | `tier` | fixed | `t2`, `t3` | 4 | 2 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_stacks_scannable` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_stacks_scanned` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_stacks_skipped` | `reason` | fixed | `paused`, `unavailable` | 3 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.run_t1; sources.gcom.fetch_all_stack_detail; sources.dataplane.probe_all literal skip sites |
| `gcinsight_scan_stacks_skipped` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_scan_stacks_total` | `tier` | fixed | `t1`, `t2`, `t3` | 4 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | scan.TIERS/run dispatch; run_t4 has only completion/duration; run_t1 alone reports carry; failure accounting is sourced by gcom/dataplane |
| `gcinsight_stack_active_series` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_stack_billed_users` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_stack_collectors_active` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_stack_fleet_fast_scrape_pipelines` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_stack_label_cardinality_findings` | `kind` | fixed | `high_confidence`, `possible` | 2 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | label_cardinality.METRIC_KIND -> pillars.risk |
| `gcinsight_stack_label_cardinality_findings` | `stack` | discovered | Not enumerated | 271 | Planning baseline is not a configured or exhaustive estate roster. | sources.gcom.fetch_inventory -> scan.run_t1/t2/t3 -> live inventory slug left joins; carry.carry_forward drops departed stacks |
| `gcinsight_usage_stacks_by_signal` | `signal` | fixed | `metrics`, `logs`, `traces`, `profiles`, `graphite` | 6 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.usage.SIGNAL_FIELDS -> build emission loop |
| `gcinsight_usage_users_last_seen_bucket` | `kind` | fixed | `7d`, `30d`, `90d`, `older`, `never` | 5 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.usage.LAST_SEEN_BUCKETS -> build |
| `gcinsight_value_adoption_ratio` | `signal` | fixed | `metrics`, `logs`, `traces`, `profiles`, `graphite` | 6 | 1 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.value imports usage.SIGNAL_FIELDS -> build emission loop |
| `gcinsight_value_benchmark` | `kind` | fixed | `active_series`, `series_per_billed_user`, `dashboards_per_user`, `stickiness`, `alert_rules`, `admin_share`, `datasource_types`, `signals_in_use`, `maturity_score`, `adaptive_adoption` | 10 | 0 unnamed slot(s). Unused capacity has no supported runtime label value. | pillars.value.BENCHMARKS -> build |

### Open upstream inputs and residual uncertainty

Assistant category/surface names and scan-failure exception-class names remain open. The five documented Assistant categories are Investigate, Observe, Dashboard, Learn and Other; Errors and the retained named surfaces reflect existing collector observations, not an exhaustive upstream contract. Unseen inputs project to lowercase other. Capitalized Other retains its existing category meaning; unknown retains the missing-surface fallback. Projected collisions are summed, preserving message/failure counts and existing selectors. The raw combination-count gauge and existing Assistant view remain unprojected.

Residual upstream taxonomy is UNKNOWN, separate from the fixed publication domains above. No future product name or exception family is inferred from an unnamed capacity slot, and neither output conformance nor selector coverage proves upstream completeness.


### Restricted runtime combinations

Unscored component/reason and dispatched skip tier/reason relations are exact, not their Cartesian capacity rectangles. Skip source witnesses are scan.run_t1, sources.gcom.fetch_all_stack_detail and sources.dataplane.probe_all.

- `gcinsight_coverage_unscored`: `component=profiles`, `reason=signal_not_in_use`
- `gcinsight_coverage_unscored`: `component=slo`, `reason=product_not_in_use`
- `gcinsight_coverage_unscored`: `component=alert`, `reason=product_not_in_use`
- `gcinsight_coverage_unscored`: `component=alert`, `reason=inventory_unavailable`
- `gcinsight_coverage_unscored`: `component=dashboard`, `reason=inventory_unavailable`
- `gcinsight_coverage_unscored`: `component=dashboard`, `reason=evidence_unavailable`
- `gcinsight_coverage_unscored`: `component=row`, `reason=ephemeral_identity`
- `gcinsight_coverage_unscored`: `component=row`, `reason=platform_identity`
- `gcinsight_coverage_unscored`: `component=row`, `reason=infrastructure_identity`
- `gcinsight_scan_stacks_skipped`: `reason=paused`, `tier=t1`
- `gcinsight_scan_stacks_skipped`: `reason=paused`, `tier=t2`
- `gcinsight_scan_stacks_skipped`: `reason=unavailable`, `tier=t2`
- `gcinsight_scan_stacks_skipped`: `reason=paused`, `tier=t3`

## Exact runtime reserves

These combinations reserve planning capacity, not runtime populations. Source-backed runner and shared-publication output contracts are tested; bounded query absence alone cannot establish a reserve.

| Metric | Labels | Contract |
|---|---|---|
| `gcinsight_carry_forward_age_seconds` | `tier=t2` | Only run_t1 reports carry-forward state. |
| `gcinsight_carry_forward_age_seconds` | `tier=t3` | Only run_t1 reports carry-forward state. |
| `gcinsight_carry_forward_age_seconds` | `tier=t4` | Only run_t1 reports carry-forward state. |
| `gcinsight_carry_forward_series` | `tier=t2` | Only run_t1 reports carry-forward state. |
| `gcinsight_carry_forward_series` | `tier=t3` | Only run_t1 reports carry-forward state. |
| `gcinsight_carry_forward_series` | `tier=t4` | Only run_t1 reports carry-forward state. |
| `gcinsight_scan_coverage_ratio` | `tier=t4` | run_t4 reads prior scans; it never composes stack accounting. |
| `gcinsight_scan_stacks_scannable` | `tier=t4` | run_t4 reads prior scans; it never composes stack accounting. |
| `gcinsight_scan_stacks_scanned` | `tier=t4` | run_t4 reads prior scans; it never composes stack accounting. |
| `gcinsight_scan_stacks_total` | `tier=t4` | run_t4 reads prior scans; it never composes stack accounting. |

## Retired metrics

No active capacity is allocated to these names.

- `gcinsight_risk_public_dashboards_total`: Never emitted; superseded by Pillar J's event-derived public count and then Pillar E's measured/enumerated/enabled/stacks enumeration family. Configured shares and observed activity are different populations.

## Rules this table enforces

- A per-stack metric carries **at most one** other label, and its enum is **≤ 4**. `stack` x `kind`(10) is 2,710 series  -  that is a table.
- A per-stack time series must carry a bounded, actionable trend. Identity-bearing or wide cross-product detail belongs in a view, even under the relaxed total ceiling.
- Label keys must be in `collector/emit/guard.py`'s allow-list. The guard is the runtime gate; this is the design-time one.

