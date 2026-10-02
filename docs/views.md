# Published view reference

Views are point-in-time tables under `views/<name>.json`, not time-series metrics. The envelope
carries rows, publication time and input provenance. T1/T2/T3 compose against fresh inventory and
hydrate only inputs they do not own; T4 independently publishes the two historical diff windows.
Missing, stale or unavailable inputs withhold dependent views and leave last-good objects intact.
A measured empty row set is different from an unavailable view. Input age, not the latest hourly
publication time, tells you how recent a daily or six-hour observation is.

This reference groups the composed publication set by user question. The dashboard reference
explains windows and live datasource panels that do not require a view. Summary views are named
measure/value tables used to contextualise the detail, not a separate evidence source. Finding
subsets reuse their parent population; a blank finding table cannot prove an unmeasured estate clean.
Identity-bearing tables require the deployment's explicit S3 privacy/access/retention acceptance.

## Estate and change

| Views | Meaning |
|---|---|
| `estate` | Per-stack configured state, user populations, resource counts, age and drift flags. |
| `estate_drift` | Stacks off the inventory's standard build; not an automatic upgrade recommendation. |
| `estate_leftovers_idle`, `estate_leftovers_billing` | Test-pattern stacks selected for idle or billable evidence; naming is a heuristic, not deletion authority. |
| `estate_diff`, `estate_diff_daily` | Seven-day and one-day comparisons with independent interval/population bounds. Missing comparison data is unknown, not no change. |

## Consumption and Adaptive Metrics/Logs

| Views | Meaning |
|---|---|
| `cost` | Measured cardinality, billed-user denominator and Adaptive rule/recommendation state per stack. |
| `cost_summary` | Consumption and Adaptive summary; rules coverage metadata qualifies subtotals independently of pricing/recommendation coverage. |
| `cost_signal_usage` | Current and billing consumption by signal, with measured above-floor populations. |
| `cost_adaptive_headroom` | Measured stacks with supported Adaptive remediation headroom, not all-series savings. |
| `cost_adaptive_metric_recommendations` | Metric-level positive add/update marginal reductions, dependencies and auto-apply evidence; no metric identity becomes a metric label. |
| `cost_adaptive_logs` | Recommendation counts and residual pending GB, including unqueried volume. No declared recommendation window supports monthly applied-savings arithmetic. |
| `cost_cardinality_outliers` | Stacks with high label cardinality and worst-label evidence; a triage list, not proof of sensitive content. |

Rules-read coverage is not recommendation or price completeness. Partial rules coverage can publish
qualified measured subtotals but no estate finding gauge/metric. Current main additionally requires
known unsegmented state for whole-stack savings and Adaptive maturity confidence. Segmented,
unknown and legacy inputs cannot turn default-only recommendations into whole-stack savings.
Positive segment marginals do not establish additivity; no combined segment saving is emitted.

## Usage, maturity and value

| Views | Meaning |
|---|---|
| `usage`, `usage_summary` | Configured resource/signal breadth, active/daily users and stickiness with summary context; not human use of every configured capability. |
| `usage_datasource_inventory` | Configured datasource type/count estate, including adjacent vendor systems; separate from types queried. |
| `usage_plugin_adoption` | Provisioned plugin prevalence, not app visits. |
| `usage_user_recency` | Measured user last-seen recency and role. |
| `usage_dormant_stacks` | Inventory stacks with `currentActiveUsers > 0` and `dailyUserCnt == 0` after missing/null counts are coerced to zero. A missing/null daily count can therefore produce a dormancy finding, not confirmed inactivity; missing active counts exclude stacks. T2 user-reader availability does not gate this predicate. |
| `maturity`, `maturity_summary` | Score, tier, partial/unscored reasons and measured-population summary. |
| `maturity_dimensions`, `maturity_rubric` | Weighted contributions and human-readable scoring rules; nonapplicable/unknown components are not zeros. |
| `maturity_owners` | Admin owner candidates and emails; only case-insensitive `@grafana.com` identities are excluded, not vendors/partners. |
| `value_adoption` | Signal adoption shares over the stated population. |
| `value_benchmarks` | Median/p90/worst unit comparisons with measured-stack counts. |
| `value_savings`, `value_summary` | Supported reduction and value measures, with missing currency when a complete price basis is unavailable. |

## Risk and operator triage

| Views | Meaning |
|---|---|
| `risk`, `risk_summary` | Combined access, collection and resource hygiene with summary context. |
| `risk_admin_sprawl`, `risk_delete_protection` | High Admin share and missing configured delete protection; not automatic removal instructions. |
| `risk_access_policies` | Policy realms, scopes and org-write exposure; discovery never authorises modifying another team's policy. |
| `risk_org_members` | Org role/MFA/staff-access metadata for governance, not session-token inventory. |
| `risk_service_accounts` | Reader-visible account/token metadata, expiry and hygiene flags, never credential values. |
| `risk_plugin_drift` | Installed/latest plugin comparison. |
| `risk_public_dashboards` | Configured public shares, including unopened shares; public access tokens are discarded. |
| `risk_alert_routing`, `risk_alert_routing_findings` | Rule/routing completeness and named rule findings. Inherited routing is exposure, not necessarily broken routing; receiver secrets are excluded. |
| `risk_fleet_dead` | Fleet registrations without supported active collection evidence. |
| `risk_fleet_attributes`, `risk_fleet_pipelines` | Bounded collector attributes and configured pipeline targeting/enabled state. |
| `risk_fleet_scrape_intervals` | Parsed faster-than-policy intervals, DPM factors and explicit unparsed evidence; not a view of unmanaged local Alloy configs. |
| `risk_label_cardinality` | Top-N high-cardinality label evidence and confidence, not an exhaustive label inventory. |
| `risk_label_hygiene`, `risk_label_hygiene_coverage` | Classified bounded raw matches and per-signal sampling limits/coverage. No-match is not clean; raw matches are restricted to this S3 view/private input, never Loki or metrics. |
| `risk_retention_stream` | Readable effective Loki selector/period/priority policy. |
| `risk_retention_change_requests` | Self-serve change requests, not proof of all effective overrides. |
| `risk_retention_policy_gaps`, `risk_retention_policy_status` | Comparison with owner-declared expectations, preserving unreadable/null outcomes rather than false compliance. |

The raw hygiene view has targeted current-object expiry under its reserved full-key prefix and
seven-day noncurrent-version expiry. Hydration resets publication age; asynchronous lifecycle is not
strict erasure since observation. See [Security](security.md) before enabling raw publication.

## Assistant and dashboard activity

| Views | Meaning |
|---|---|
| `ai_assistant`, `ai_summary` | Per-stack rolling 30-day Assistant observations and measured summary; not the live billing-period window. |
| `ai_category_surface` | Categorised message split by surface/human-driven enum, with uncategorised remainder accounted separately. |
| `ai_tenant_config` | Readable tenant objects and enablement metadata, never another user's private skills/rules. |
| `ai_credential_coverage` | Credential/read state and actionable coverage context, not a token list. |
| `ai_enablement_gap` | Measured Assistant use without tenant configuration. |
| `ai_token_outliers` | Tokens-per-user outliers within the measured population. |
| `ai_mcp_auth_failed`, `ai_config_disabled` | Tenant integrations with reported auth failures and objects configured off. |
| `insights_dashboard_usage`, `insights_summary` | Rolling 24-hour opens, per-stack viewers, query/cache/error counts and measured summary. Summed stack viewers are not org-unique people. |
| `insights_top_dashboards` | Most-opened dashboard identities in the observed window. |
| `insights_public_dashboards` | Public shares observed opened, separate from configured public inventory. |
| `insights_datasource_types` | Queried backend types, request duration and errors; backend type is not app identity. |
| `insights_query_mix` | Per-stack top-20 datasource types/panel plugin IDs, remainder and distinct counts; requests are not visits. |
| `insights_coverage` | Stack reader/query availability for activity interpretation. |
| `insights_surface_usage`, `insights_surface_usage_estate` | Request counts by closed source enum per stack and measured estate; `scenes` does not identify individual apps. |
| `insights_surface_unmapped` | Unmapped source request evidence, not invented app attribution. |
| `insights_dashboard_opening_31d` | Configured dashboard catalogue joined with a separate 31-day open observation and explicit coverage state. |
| `insights_datasource_query_cost` | Datasource inventory joined with observed cumulative query duration/cache evidence, not a bill or monetary price. |

## Coverage and optional configured products

| Views | Meaning |
|---|---|
| `coverage_service_register` | Canonical service identities with signal/component evidence, applicable weighted completeness, explicit dashboard/alert relationships and unscored reasons. |
| `coverage_technology_register`, `coverage_metric_name_register` | Technology sentinel matches and named metric evidence with registry version; unmatched names do not prove a technology. |
| `coverage_cluster_register` | Observed cluster identities, not all configured infrastructure. |
| `coverage_legacy_service_register` | Legacy generic service labels, kept distinct from canonical identity. |
| `coverage_summary` | Discovered/retained service, technology, cluster and unmatched-name counts by stack. |
| `coverage_capability_adoption`, `coverage_capability_opportunities` | Measured capability production and eligible outreach gaps, with explicit population/window. |
| `coverage_producing_signals` | Metrics/Traces 24-hour peaks from documented usage series; missing is unknown, returned zero is measured zero, positive is backend production not UI use. |
| `coverage_adaptive_traces_inventory` | Config availability and policy/pending recommendation counts with independent domain state; not enablement or achieved savings. |
| `coverage_slo_inventory` | Optional configured definition/alerting and closed source/status counts, not SLI history. |
| `coverage_synthetic_inventory` | Optional checks by type/enabled state and probes by public/private class, not execution/results. |
| `faro_apps` | Optional configured web/mobile/unknown app counts, not frontend adoption. |
| `ml_jobs` | Optional configured forecast-job counts, not predictions or forecast accuracy. |
| `cloud_accounts` | Optional AWS configured-account counts only; other providers remain unknown. |
| `pdc_networks` | Optional stack-attributed PDC signing-policy counts after complete region/page reads, not connection activity. |
| `reports_inventory` | Optional configured reports including disabled objects, not delivery/execution. |
| `irm_integrations` | Counter implementation exists, but acceptance is parked on HTTP 206 handling; not an accepted delivered inventory. |

Optional tables/tabs are omitted only when their objects are genuinely missing. Retained older views
remain readable and visibly age; permission, transport and parse errors remain explicit. Product
families are default-off and require separate approval. All product detail/identity is discarded
from count outputs; transient receipt is not memory erasure. [Configuration](configuration.md#optional-product-readers)
and [CAPABILITIES](../CAPABILITIES.md#optional-count-only-product-inputs) give tokens, routes, exact
pairs and risks. Library/playlist empty controls remain parked; k6 has no admitted collector route.
