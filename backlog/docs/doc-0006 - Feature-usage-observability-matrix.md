---
id: doc-0006
title: Feature usage observability matrix
type: specification
created_date: '2026-09-23 18:33'
updated_date: '2026-09-23 18:56'
---
# Feature usage observability matrix - wave 1 evidence, 2026-09-23

This matrix answers the field question by separating availability, configuration, production and use by people. L1 = available or entitled, L2 = configured objects, L3 = producing data, L4 = human query or open activity. Each ceiling below is the best signal reachable through the named source, not a claim that the current collector publishes it. The estate is discovered live. A row marked unverified must not be presented as measured coverage. Routes are read-only candidates only; this document grants no new action or scope.

Live method: the root enumerated `grafanacloud_*` names through the write-stack `grafanacloud-usage` datasource in two orgs (310 customer-side names, 171 development names, 325-name union), queried usage-insights with an exact `instance_id` guard on 50 customer and five development stacks, and checked existing stack-local GET routes on six customer and three development stacks. The stack sample was chosen from larger dashboard estates with working readers. It is not a random or estate-wide completeness claim. `stack_id` is present on 224 of the 310 customer metric names and 168 of the 171 development names. The exact name roster and classification are appended below. A metric's presence proves it exists on the write datasource, not that every stack has a nonzero value.

| Product and sub-feature | Best defensible fidelity | Source, exact route or query | Credential and action/scope | Live verification and limit | Granularity | Series cost | Recommendation |
|---|---|---|---|---|---|---|---|
| Metrics ingestion, active series, native histograms, exemplars | L3 | `grafanacloud-usage` `grafanacloud_instance_active_series`, `...active_native_histogram_series`, `...exemplars_per_second`; stack Mimir `/api/prom/api/v1/label/__name__/values` | Write-stack reader `datasources:query` at `datasources:uid:grafanacloud-usage`; org CAP `metrics:read` | Metric family live on both write stacks (2). Rates require a window; active series do not prove query use. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034: bounded producing-signal view |
| Logs ingestion, streams, retention, Adaptive Logs | L3 | `grafanacloud_logs_instance_*`; Loki limits `/config/tenant/v1/limits`; Adaptive Logs `GET /api/plugin-proxy/grafana-adaptivelogs-app/recommendations` | Write-stack usage reader; org CAP `logs:read`; stack reader Adaptive Logs plugin access and patterns read | Usage names live (2); Adaptive Logs GET 200 on nine sampled stacks, one list empty. A 200/empty result is not an estate zero. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for producing signal; retain existing Adaptive Logs collector |
| Traces ingestion, span metrics, service graphs, Adaptive Traces | L3 | `grafanacloud_traces_instance_*`, `grafanacloud_instance_active_spanmetrics_series`; Tempo `/tempo/api/v2/search/tags`; Adaptive Traces plugin resources | Write-stack usage reader; org CAP `traces:read`; stack reader Adaptive Traces plugin read pairs | Usage names live (2); policy route not reverified here. Ingestion does not prove Traces UI use. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for producing signal; retain existing adaptive collector |
| Profiles ingestion and continuous profiling | L3 | `grafanacloud_profiles_instance_*`; current Pyroscope `querier.v1.QuerierService/LabelValues` | Write-stack usage reader; org CAP `profiles:read` | Usage names live (2); broader profile query access unverified. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for producing signal; retain existing profile evidence |
| Metrics, Logs, Traces and Profiles Drilldown individually | L4 only with a discriminator not found | Usage-insights `GET /api/datasources/proxy/uid/grafanacloud-usage-insights/loki/api/v1/query`, `source="scenes"` | Per-stack reader `datasources:query` at `datasources:uid:grafanacloud-usage-insights` | `scenes` live on 55 stacks. Inspected lines lack plugin or URL; `datasourceType` is a weak inference, never per-app attribution. | Per stack and estate; identified-user counts only inside Loki | 0 new series; view or direct query | GCI-0040: find discriminator before per-app claim |
| Application Observability services and service map | L3 for telemetry; L2 inventory candidate | `grafanacloud_app_observability_*`, service/span-metric series; plugin `/api/plugins/grafana-app-observability-app/resources/*` path unverified | Write usage reader and org CAP `metrics:read`; product plugin reader action/scope unknown and absent | Metric family live (2); service map API unverified. Services are not UI visits. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for signals; GCI-0041 before object inventory |
| Application Observability OTel, Beyla or Tempo generator provenance | L3 candidate | Mimir service and span-metric labels, Fleet collector inventory | Org CAP `metrics:read`, `fleet-management:read` | Not live verified in this wave; a series without explicit producer label cannot prove the instrumentation path. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0034 only where a producer label proves source |
| Knowledge Graph entities, assertions and integrations | L3 for entity series; L2 inventory candidate | `grafanacloud_asserts_*`, `asserts:*`; `/api/plugins/grafana-asserts-app/resources/*` path unverified | Write usage reader or org CAP `metrics:read`; KG plugin reader action/scope absent, exact pair unresolved | Usage names live (2); app route unverified. Populated graph is not workbench use. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for signals; GCI-0041 before object inventory |
| Knowledge Graph RCA workbench use and KG-backed SLOs | L2 for SLO source; L4 unavailable for RCA use | SLO `GET /api/plugins/grafana-slo-app/resources/v1/slo` then `searchExpression`; usage-insights scenes is not discriminating | Needs `grafana-slo-app.slo:read`, `grafana-slo-app.orgpreferences:read`, plugin access on SLO id; absent | SLO GET 403 on 3 dev and 6 customer stacks. No RCA-specific event identified. | Per stack and estate; identified-user counts only inside Loki | 0 new series; view or direct query | GCI-0036 after scope; GCI-0040 for workbench use |
| Synthetic Monitoring checks by type, probes and check alerts | L2 candidate; L3 execution metrics | SM `GET <backend>/api/v1/check`, candidate `/api/v1/probe` and `/api/v1/alert`; `grafanacloud_sm_*`, `sm_check_info` | Separate SM API token and app checks/probes/alerts reader pairs, absent; write usage reader for metrics | Usage metric names live (2). SM object API not queried; result inventory remains unproven. Check execution is automation. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0037 after GCI-0041 scope decision |
| k6 projects, tests, runs, browser tests and execution mode | L2 candidate; L3 VUh | `GET /cloud/v6/projects`, `/cloud/v6/test_runs`, `/cloud/v6/load_tests/{id}/test_runs`; `grafanacloud_k6_stack_virtual_user_hours_usage` | k6 token/role unresolved; write usage reader has usage metric | VUh name live (2), current billing-period cumulative semantics documented in source. k6 API not queried; do not download scripts. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0038 after GCI-0041 scope decision |
| Frontend Observability apps, sessions and sourcemaps | L3 sessions; L2 app inventory candidate | `grafanacloud_frontend_observability_instance_sessions_per_second`; plugin `/api/plugins/grafana-kowalski-app/resources/*` unverified | Write usage reader; Frontend plugin viewer absent; no safe sourcemap list route established | Session metric live (2); app and sourcemap routes unverified. Sessions do not prove Grafana UI use. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for sessions; GCI-0041 before app inventory; no sourcemap read |
| Kubernetes Monitoring clusters, Alloy versions and cost features | L3 telemetry; L2 cluster candidate | `kube_*`, Alloy build/version series, Fleet ListCollectors, `grafanacloud_infra_observability_*`; `grafana-k8s-app` plugin route unverified | Org CAP `metrics:read` and `fleet-management:read`; K8s plugin reader absent | Infra usage names live (2). `grafana-k8s-app` request source observed on customer sample, 78 requests in 7d; no complete cluster or Helm inventory. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for signals; GCI-0041 before app inventory |
| SLO count, alerting and metrics versus KG source | L2 candidate | `GET /api/plugins/grafana-slo-app/resources/v1/slo` | Needs SLO read, orgpreferences read and plugin access; existing reader has only folder read | HTTP 403 on all nine sampled stacks, so object count is unknown. Recording series may prove L3 but not source completeness. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0036 after GCI-0041 scope decision |
| IRM OnCall integrations, escalation chains, schedules and alert groups | L2 candidate; L3 historical group activity | `GET <IRM API>/api/v1/integrations/`, candidate `/escalation_chains/`, `/schedules/`, `/alert_groups/`; `grafanacloud_oncall_instance_alert_groups_total` | IRM integration and related reader pairs plus plugin access absent; write usage reader for counter | OnCall counter name live (2). IRM API not queried; historical cumulative value is not current activity. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0039 after GCI-0041 scope decision |
| IRM Incident declared incidents | L2 candidate | `/api/plugins/grafana-irm-app/resources/api/v1` Incident RPC | IRM reader pairs absent; read RPC uses POST and cannot enter the collector GET-only client without a new contract | Not live verified. Do not treat missing reader access as zero incidents. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0039 after explicit read-RPC and scope decision |
| Grafana alert rules, recording rules and contact point types | L2; evaluation L3 | `GET /api/v1/provisioning/alert-rules`, `/api/v1/provisioning/contact-points`; Mimir `/api/prom/api/v1/rules` | Stack `alert.rules:read` at `folders:*`, receiver read at `receivers:*`; org CAP `rules:read` | Alert-rule GET 200 with populated lists on nine sampled stacks. Receiver secrets are refused; inherited policy matters. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain existing collector; refine views only on evidence |
| Assistant requests, users, skills, rules, automations and integrations | L4 aggregate query activity; L2 objects | usage-insights `source="grafana-assistant-app"`; existing Assistant plugin resource usage/inventory routes | Per-stack usage query pair and Assistant plugin read actions are present | Source live across sample; 22 dev and 392 customer requests over 7d. It counts data requests, not prompts or conversations. | Per stack and estate; identified-user counts only inside Loki | 0 new series; view or direct query | Retain Pillar I; surface requests in GCI-0032.01 |
| Investigations and watcher agents | Aggregate count only; personal inventory unavailable | Existing Assistant plugin usage route; `/api/v2/investigations` and `/api/v1/watcher-agents` are known false-pass/rejected routes | Existing Assistant read actions | Existing source contract: investigations list may report zero to an SA, watcher route 403 by identity design. Not reverified this wave. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain aggregate only; personal inventory unavailable to reader |
| Adaptive Metrics rules, recommendations, exemptions and segments | L2; L3 applied savings | Mimir `/aggregations/rules`, `/aggregations/recommendations?verbose=true`, config and segment routes; plugin exemptions | Org CAP Adaptive Metrics reads; stack plugin exemptions read pair | Existing collector contract, not reverified here. Default recommendation omits counts required for savings. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain existing collector and verbose savings rule |
| Adaptive Logs rules and recommendations | L2 | `GET /api/plugin-proxy/grafana-adaptivelogs-app/recommendations` | Existing stack plugin access and patterns read | HTTP 200 on nine sampled stacks, including one empty list. No declared recommendation time window. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain existing collector and its window caveat |
| Adaptive Traces policies and recommendations | L2 | Candidate `/api/plugins/grafana-adaptivetraces-app/resources/*`; usage metric family | Existing stack policies/recommendations/config read pairs, no write | Metric names live (2); plugin route not verified. The product role bundles writes, so it must not be assigned wholesale. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain existing reader contract; verify route before expansion |
| Adaptive Profiles | L1 or L3 candidate | No safe dedicated read route established; Pyroscope label route is separate | Org CAP `profiles:read`; dedicated app pair absent | Not live verified, no adoption claim. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | No build until a read route and permission contract are proven |
| Fleet collectors, pipelines and remote config in use | L2; L3 active collector match | `collector.v1.CollectorService/ListCollectors`, `pipeline.v1.PipelineService/ListPipelines` | Org CAP `fleet-management:read`; read routes use POST Connect-RPC | Existing collector contract, not reverified this wave. Inactive registrations and unbound pipelines inflate counts. | Org, collector and estate rollup | 0 new series; view or direct query | Retain existing active-collector join |
| Cloud Provider Observability AWS, Azure and GCP | L1 plugin; L2 candidate | Plugin inventory `GET /api/plugins`; product resource route not established | Stack `plugins.app:access` and product reader pairs absent; exact pair unresolved | Plugin list populated on nine sampled stacks, not a config or usage inventory. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0041 before product object inventory |
| Integrations and Connections | L2 datasource objects only | `GET /api/datasources`; product-specific integrations route unverified | Existing stack `datasources:read` at `datasources:*`; product plugin reader pair unresolved | Datasource lists populated on nine sampled stacks. A datasource is not a used integration. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain datasource inventory; do not claim integration use |
| Database Observability | L3 metric family; L1 plugin | `grafanacloud_instance_active_dbo11y_*`; candidate app resources unverified | Write usage reader; product plugin reader pair absent | Dev-only metric names live (1); no object or human-use route verified. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0034 for signal; GCI-0041 before object inventory |
| Private Data Source Connect | L1 connection; L2 network candidate | `grafanacloud_grafana_pdc_connected_agents`; plugin resource route unverified | Write usage reader; private-networks reader pair absent | Metric name live (2). Connected agent is not a query or app visit; network tokens must not be read. | Per stack where `stack_id` exists; otherwise org or estate | 0 new series; view or direct query | GCI-0041 before network inventory; do not read tokens |
| Machine Learning forecasts, outlier detection and Sift | L1 plugin; L2 object candidate | Product plugin resources unverified | ML viewer and Sift viewer roles absent; exact read pairs unresolved | Not live verified; no use claim. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0041 before product object inventory |
| Explore and correlations | L4 query activity only | usage-insights guarded `data-request.source` | Per-stack usage query pair exists | Explore source live; correlations not observed in sample. Neither has upstream `error`, so no error rate. A page without a query is invisible. | Per stack and estate; identified-user counts only inside Loki | 0 proposed; GCI-0032.01 already declares 2 x 8 bounded estate series | GCI-0032.01 for bounded request surfaces; no error-rate claim |
| Notebooks and panel editor | L4 query candidate | usage-insights `source`; notebook object route unverified | Per-stack usage query pair exists; notebook reader unknown | Not observed in sample. Upstream suppresses `editPanel` requests, so panel editor count is incomplete. | Per stack and estate; identified-user counts only inside Loki | 0 new series; view or direct query | No build until event or safe inventory route is proven |
| Dashboards, public dashboards and snapshots | L2 config; L4 opens | `GET /api/search/`, `/api/dashboards/public-dashboards`; guarded `dashboard-view` | Stack dashboard/folder/snapshot read pairs and usage query pair exist | Search populated on nine stacks; dashboard source live on 55. A public share may exist with no views. Do not persist public tokens. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | Retain Pillar J dashboard inventory and opens |
| Reporting, library panels and playlists | L2 candidate | `GET /api/reports`, `/api/library-elements`, `/api/playlists` | `reports:read` at `reports:*`, library-elements read pair, `playlists:read` are absent or unresolved | Not queried. Scheduled objects do not prove playback, reading or report delivery. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0041 before object inventory |
| Git sync and dashboard provisioning | L2 candidate | Version-specific provisioning API, not established; dashboard detail alone lacks source repository | Provisioning read pair absent or unresolved | Not live verified. A dashboard's existence does not establish Git sync. | Per stack objects; estate rollup only after complete inventory | 0 new series; view or direct query | GCI-0041 before object inventory |

## What is trackable

- **Today:** per-stack and estate aggregate query surfaces where `source` is discriminating; dashboard opens; configured Grafana dashboards, public shares, alert rules and datasources; ingest and billing-side signals with a stated window; existing Assistant, Fleet and adaptive collector outputs. The current wave implements the bounded surface breakdown separately under GCI-0032.01.
- **After follow-on work and a scope decision:** typed Synthetic Monitoring checks, SLO objects/source, IRM inventory, k6 runs, product app object counts, and additional live metric-based producing signals. Any new metric must justify a time series. Otherwise use a point-in-time view at zero series cost.
- **Not visible from available sources:** per-app use inside generic `scenes`; app landing-page visits without a query; personal investigations or user-scoped Assistant objects from a service account; a person using a product merely from its ingestion or billing signal; complete source code or sourcemap inventory without reading sensitive material.

## Scope and cost decision

No reader role, policy, token or service account was changed. The product-plugin pairs listed in the rows above are candidates for one explicit decision task. New scopes reach customer configuration and sometimes identities, endpoints or secrets. Any change must keep basic role `None`, preserve `datasources:query` pins, use per-product action/scope pairs and independently verify output minimization. The initial follow-on ranking favours point-in-time views (zero emitted series) and panels over the existing usage datasource (zero collector series); a per-stack enum metric costs `live stacks x enum size` and needs a real trend or alert use case.

## Primary route references

The route and role candidates above are grounded in current official product documentation. An undocumented plugin `resources/*` path remains a candidate even when a related role appears in the role catalogue.

- [Grafana Cloud app plugin roles](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/access-control/plugin-role-definitions/) and [app-plugin RBAC](https://grafana.com/docs/grafana-cloud/platform/security-and-account-management/security-and-access/authentication-and-permissions/access-control/rbac-for-app-plugins/) - named plugin readers and the difference between plugin access and product actions.
- [SLO API](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/slo/set-up/api/) and [SLO RBAC](https://grafana.com/docs/grafana-cloud/observe-and-act/alert-and-measure-reliability/slo/set-up/rbac/) - the documented GET and SLO reader permissions.
- [Synthetic Monitoring API](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/api-reference/) and [Synthetic Monitoring roles](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/user-and-team-management/) - separate backend/token and checks-reader contract.
- [k6 Cloud REST API](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/k6/reference/cloud-rest-api/), [projects](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/k6/reference/cloud-rest-api/projects/), [test runs](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/k6/reference/cloud-rest-api/test-runs/) and [k6 RBAC](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/k6/projects-and-users/configure-rbac/) - projects/runs candidates and separate reader role.
- [OnCall integrations API](https://grafana.com/docs/grafana-cloud/observe-and-act/respond-to-incidents/reference/oncall-api/integrations/), [IRM permissions](https://grafana.com/docs/grafana-cloud/observe-and-act/respond-to-incidents/set-up/manage-access/roles-and-permissions/) and [Incident API](https://grafana.com/docs/grafana-cloud/observe-and-act/respond-to-incidents/reference/incident-api/get-started/) - inventory GET and Incident read-RPC distinctions.
- [Kubernetes Monitoring access](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-infrastructure/kubernetes-monitoring/configuration/control-access/), [Frontend Observability RBAC](https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/frontend-observability/settings-and-policies/rbac/), [Fleet API](https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/fleet-management/api-reference/) - product role and collector read boundaries.
- [Library Element API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/library_element/), [Reporting API](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/http-api/api-legacy/reporting/), [Git Sync](https://grafana.com/docs/grafana/latest/as-code/observability-as-code/git-sync/use-git-sync/) - core configuration candidates.

## Metric-name appendix

Each row below is one live-enumerated name from the union of the two write-stack datasources. `C` and `D` mean it appeared in the customer and development write datasource respectively; they are not per-stack nonzero evidence. `stack_id` records label presence in that datasource. Product and cue come from the name, not a vendor metric contract. `rate` is supported by explicit per-second or recorded-rate syntax. `billing quantity` has an unverified window except for the k6 VUh series noted above. `counter candidate`, `gauge candidate` and `unknown` explicitly require a metric-specific contract before use in a collector calculation.

| Metric | Product family | Sub-feature cue from name | Shape | C/D | `stack_id` C/D |
|---|---|---|---|---|---|
| `grafanacloud_ai_tokens_active_users` | AI tokens | ai tokens active users | gauge candidate | C | yes/- |
| `grafanacloud_ai_tokens_overage` | AI tokens | ai tokens overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_ai_tokens_total_tokens` | AI tokens | ai tokens total tokens | unknown | C | yes/- |
| `grafanacloud_ai_tokens_user_total_tokens` | AI tokens | ai tokens user total tokens | unknown | C | yes/- |
| `grafanacloud_app_observability_billable_usage` | Application Observability | app observability billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_app_observability_hostless_service_entity_count` | Application Observability | app observability hostless service entity count | gauge candidate | CD | yes/yes |
| `grafanacloud_app_observability_overage` | Application Observability | app observability overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_app_observability_service_entity_count` | Application Observability | app observability service entity count | gauge candidate | CD | yes/yes |
| `grafanacloud_asserts_instance_active_entities` | Knowledge Graph | asserts instance active entities | gauge candidate | CD | yes/yes |
| `grafanacloud_asserts_instance_total_entities` | Knowledge Graph | asserts instance total entities | unknown | CD | yes/yes |
| `grafanacloud_assistant_active_users` | Assistant | assistant active users | gauge candidate | C | yes/- |
| `grafanacloud_assistant_overage` | Assistant | assistant overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_assistant_users` | Assistant | assistant users | unknown | C | yes/- |
| `grafanacloud_frontend_observability_billable_usage` | Frontend Observability | frontend observability billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_frontend_observability_instance_app_logs_bytes_received_per_second` | Frontend Observability | frontend observability instance app logs bytes received per second | rate | CD | yes/yes |
| `grafanacloud_frontend_observability_instance_app_traces_bytes_received_per_second` | Frontend Observability | frontend observability instance app traces bytes received per second | rate | CD | yes/yes |
| `grafanacloud_frontend_observability_instance_logs_bytes_received_per_second` | Frontend Observability | frontend observability instance logs bytes received per second | rate | CD | yes/yes |
| `grafanacloud_frontend_observability_instance_sessions_per_second` | Frontend Observability | frontend observability instance sessions per second | rate | CD | yes/yes |
| `grafanacloud_frontend_observability_instance_traces_bytes_received_per_second` | Frontend Observability | frontend observability instance traces bytes received per second | rate | CD | yes/yes |
| `grafanacloud_frontend_observability_overage` | Frontend Observability | frontend observability overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_grafana_instance_active_user_count` | Grafana core | grafana instance active user count | gauge candidate | CD | yes/yes |
| `grafanacloud_grafana_instance_active_users` | Grafana core | grafana instance active users | gauge candidate | C | yes/- |
| `grafanacloud_grafana_instance_alerting_alertmanager_alerts` | Grafana core | grafana instance alerting alertmanager alerts | unknown | CD | yes/yes |
| `grafanacloud_grafana_instance_alerting_alerts` | Grafana core | grafana instance alerting alerts | unknown | CD | yes/yes |
| `grafanacloud_grafana_instance_alerting_rule_evaluation_failures_total:rate5m` | Grafana core | grafana instance alerting rule evaluation failures total:rate5m | rate | CD | yes/yes |
| `grafanacloud_grafana_instance_alerting_rule_evaluations_total:rate5m` | Grafana core | grafana instance alerting rule evaluations total:rate5m | rate | CD | yes/yes |
| `grafanacloud_grafana_instance_alerting_rule_group_rules` | Grafana core | grafana instance alerting rule group rules | unknown | CD | yes/yes |
| `grafanacloud_grafana_instance_alerting_silences` | Grafana core | grafana instance alerting silences | unknown | CD | yes/yes |
| `grafanacloud_grafana_instance_alerting_state_history_writes_failed_total:rate5m` | Grafana core | grafana instance alerting state history writes failed total:rate5m | rate | CD | yes/yes |
| `grafanacloud_grafana_instance_billable_users` | Grafana core | grafana instance billable users | billing quantity, window unverified | C | yes/- |
| `grafanacloud_grafana_instance_created_date` | Grafana core | grafana instance created date | gauge candidate | CD | yes/yes |
| `grafanacloud_grafana_instance_custom_datasource_count` | Grafana core | grafana instance custom datasource count | gauge candidate | CD | yes/yes |
| `grafanacloud_grafana_instance_dashboard_count` | Grafana core | grafana instance dashboard count | gauge candidate | CD | yes/yes |
| `grafanacloud_grafana_instance_info` | Grafana core | grafana instance info | gauge candidate | CD | yes/yes |
| `grafanacloud_grafana_instance_overage` | Grafana core | grafana instance overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_grafana_instance_plugin_overage` | Grafana core | grafana instance plugin overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_grafana_instance_resource_quota_limit` | Grafana core | grafana instance resource quota limit | gauge candidate | CD | yes/yes |
| `grafanacloud_grafana_instance_resource_quota_usage` | Grafana core | grafana instance resource quota usage | billing quantity, window unverified | CD | yes/yes |
| `grafanacloud_grafana_pdc_connected_agents` | Private Data Source Connect | grafana pdc connected agents | unknown | CD | yes/yes |
| `grafanacloud_infra_observability_containers_billable_usage` | Infrastructure Observability | infra observability containers billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_infra_observability_containers_overage` | Infrastructure Observability | infra observability containers overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_infra_observability_hosts_billable_usage` | Infrastructure Observability | infra observability hosts billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_infra_observability_hosts_overage` | Infrastructure Observability | infra observability hosts overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_instance_active_asserts_alerts` | Knowledge Graph | instance active asserts alerts | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_asserts_series` | Knowledge Graph | instance active asserts series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_caas_targets_series` | Metrics and stack backend | instance active caas targets series | gauge candidate | C | yes/- |
| `grafanacloud_instance_active_cadvisor_version_info_series` | Metrics and stack backend | instance active cadvisor version info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_collector_spanmetrics_series` | Metrics and stack backend | instance active collector spanmetrics series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_dbo11y_instance_count` | Database Observability | instance active dbo11y instance count | gauge candidate | D | -/yes |
| `grafanacloud_instance_active_dbo11y_series` | Database Observability | instance active dbo11y series | gauge candidate | D | -/yes |
| `grafanacloud_instance_active_dbo11y_stats` | Database Observability | instance active dbo11y stats | gauge candidate | D | -/yes |
| `grafanacloud_instance_active_faas_targets_series` | Metrics and stack backend | instance active faas targets series | gauge candidate | C | yes/- |
| `grafanacloud_instance_active_host_info_series` | Metrics and stack backend | instance active host info series | gauge candidate | D | -/yes |
| `grafanacloud_instance_active_influx_series` | Metrics and stack backend | instance active influx series | gauge candidate | C | yes/- |
| `grafanacloud_instance_active_integration_host_series` | Metrics and stack backend | instance active integration host series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_integration_series` | Metrics and stack backend | instance active integration series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_kube_node_info_series` | Metrics and stack backend | instance active kube node info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_kube_pod_container_info_series` | Metrics and stack backend | instance active kube pod container info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_kube_pod_info_series` | Metrics and stack backend | instance active kube pod info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_legacy_collector_spanmetrics_series` | Metrics and stack backend | instance active legacy collector spanmetrics series | gauge candidate | C | yes/- |
| `grafanacloud_instance_active_native_histogram_buckets` | Metrics and stack backend | instance active native histogram buckets | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_native_histogram_series` | Metrics and stack backend | instance active native histogram series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_node_uname_info_series` | Metrics and stack backend | instance active node uname info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_otlp_series` | Metrics and stack backend | instance active otlp series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_series` | Metrics and stack backend | instance active series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_service_graph_series` | Metrics and stack backend | instance active service graph series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_servicegraphmetrics_classic_histograms_series` | Metrics and stack backend | instance active servicegraphmetrics classic histograms series | gauge candidate | C | yes/- |
| `grafanacloud_instance_active_servicegraphmetrics_native_histograms_series` | Metrics and stack backend | instance active servicegraphmetrics native histograms series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_spanmetrics_classic_histograms_series` | Metrics and stack backend | instance active spanmetrics classic histograms series | gauge candidate | C | yes/- |
| `grafanacloud_instance_active_spanmetrics_native_histograms_series` | Metrics and stack backend | instance active spanmetrics native histograms series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_spanmetrics_series` | Metrics and stack backend | instance active spanmetrics series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_target_info_series` | Metrics and stack backend | instance active target info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_traces_host_info_series` | Traces | instance active traces host info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_traces_target_info_series` | Traces | instance active traces target info series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_active_unidentifiable_targets_series` | Metrics and stack backend | instance active unidentifiable targets series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_aggregation_aggregated_samples_total:rate5m` | Metrics and stack backend | instance aggregation aggregated samples total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_aggregation_aggregated_series` | Metrics and stack backend | instance aggregation aggregated series | unknown | CD | yes/yes |
| `grafanacloud_instance_aggregation_raw_samples_total:rate5m` | Metrics and stack backend | instance aggregation raw samples total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_aggregation_raw_series` | Metrics and stack backend | instance aggregation raw series | unknown | CD | yes/yes |
| `grafanacloud_instance_alertmanager_alerts` | Metrics and stack backend | instance alertmanager alerts | unknown | CD | yes/yes |
| `grafanacloud_instance_alertmanager_config_last_reload_successful` | Metrics and stack backend | instance alertmanager config last reload successful | unknown | CD | yes/yes |
| `grafanacloud_instance_alertmanager_created_date` | Metrics and stack backend | instance alertmanager created date | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_info` | Metrics and stack backend | instance alertmanager info | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_invalid_config` | Metrics and stack backend | instance alertmanager invalid config | unknown | CD | yes/yes |
| `grafanacloud_instance_alertmanager_notifications_failed_per_integration_per_second` | Metrics and stack backend | instance alertmanager notifications failed per integration per second | rate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_notifications_failed_per_second` | Metrics and stack backend | instance alertmanager notifications failed per second | rate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_notifications_failed_total` | Metrics and stack backend | instance alertmanager notifications failed total | counter candidate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_notifications_per_second` | Metrics and stack backend | instance alertmanager notifications per second | rate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_notifications_total` | Metrics and stack backend | instance alertmanager notifications total | counter candidate | CD | yes/yes |
| `grafanacloud_instance_alertmanager_silences` | Metrics and stack backend | instance alertmanager silences | unknown | CD | yes/yes |
| `grafanacloud_instance_app_o11y_host_count` | Application Observability | instance app o11y host count | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_app_o11y_host_v2_count` | Application Observability | instance app o11y host v2 count | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_app_o11y_host_v3_count` | Application Observability | instance app o11y host v3 count | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_attributed_active_series` | Metrics and stack backend | instance attributed active series | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_attributed_billable_usage` | Metrics and stack backend | instance attributed billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_instance_attributed_overage` | Metrics and stack backend | instance attributed overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_instance_attributed_samples_per_second` | Metrics and stack backend | instance attributed samples per second | rate | CD | yes/yes |
| `grafanacloud_instance_billable_usage` | Metrics and stack backend | instance billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_instance_created_date` | Metrics and stack backend | instance created date | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_exemplars_discarded_per_second` | Metrics and stack backend | instance exemplars discarded per second | rate | CD | yes/yes |
| `grafanacloud_instance_exemplars_per_second` | Metrics and stack backend | instance exemplars per second | rate | CD | yes/yes |
| `grafanacloud_instance_ha_tracker_elected_replica_changes_total` | Metrics and stack backend | instance ha tracker elected replica changes total | counter candidate | C | yes/- |
| `grafanacloud_instance_info` | Metrics and stack backend | instance info | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_memory_series` | Metrics and stack backend | instance memory series | unknown | CD | yes/yes |
| `grafanacloud_instance_metadata_discarded_per_second` | Metrics and stack backend | instance metadata discarded per second | rate | C | yes/- |
| `grafanacloud_instance_metadata_per_second` | Metrics and stack backend | instance metadata per second | rate | CD | yes/yes |
| `grafanacloud_instance_metrics_limits` | Metrics and stack backend | instance metrics limits | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_native_histogram_buckets_multiplier_wip` | Metrics and stack backend | instance native histogram buckets multiplier wip | unknown | CD | yes/yes |
| `grafanacloud_instance_overage` | Metrics and stack backend | instance overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_instance_product_active_series` | Metrics and stack backend | instance product active series | gauge candidate | D | -/yes |
| `grafanacloud_instance_product_samples_per_second` | Metrics and stack backend | instance product samples per second | rate | CD | yes/yes |
| `grafanacloud_instance_queries_per_second` | Metrics and stack backend | instance queries per second | rate | CD | yes/yes |
| `grafanacloud_instance_recommendations_estimated_savings_series` | Metrics and stack backend | instance recommendations estimated savings series | unknown | CD | yes/yes |
| `grafanacloud_instance_rule_config_last_reload_successful` | Metrics and stack backend | instance rule config last reload successful | unknown | CD | yes/yes |
| `grafanacloud_instance_rule_evaluation_failures_total:rate5m` | Metrics and stack backend | instance rule evaluation failures total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_rule_evaluations_total:rate5m` | Metrics and stack backend | instance rule evaluations total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_rule_group_interval_seconds` | Metrics and stack backend | instance rule group interval seconds | unknown | CD | yes/yes |
| `grafanacloud_instance_rule_group_iterations_missed_total:rate5m` | Metrics and stack backend | instance rule group iterations missed total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_rule_group_iterations_total:rate5m` | Metrics and stack backend | instance rule group iterations total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_rule_group_last_duration_seconds` | Metrics and stack backend | instance rule group last duration seconds | unknown | CD | yes/yes |
| `grafanacloud_instance_rule_group_last_evaluation_timestamp_seconds` | Metrics and stack backend | instance rule group last evaluation timestamp seconds | gauge candidate | CD | yes/yes |
| `grafanacloud_instance_rule_group_rules` | Metrics and stack backend | instance rule group rules | unknown | CD | yes/yes |
| `grafanacloud_instance_ruler_notifications_errors_total:rate5m` | Metrics and stack backend | instance ruler notifications errors total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_ruler_notifications_latency_seconds:50quantile` | Metrics and stack backend | instance ruler notifications latency seconds:50quantile | unknown | CD | yes/yes |
| `grafanacloud_instance_ruler_notifications_latency_seconds:99quantile` | Metrics and stack backend | instance ruler notifications latency seconds:99quantile | unknown | CD | yes/yes |
| `grafanacloud_instance_ruler_notifications_queue_capacity` | Metrics and stack backend | instance ruler notifications queue capacity | unknown | CD | yes/yes |
| `grafanacloud_instance_ruler_notifications_queue_length` | Metrics and stack backend | instance ruler notifications queue length | unknown | CD | yes/yes |
| `grafanacloud_instance_ruler_notifications_sent_total:rate5m` | Metrics and stack backend | instance ruler notifications sent total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_ruler_queries_failed_total:rate5m` | Metrics and stack backend | instance ruler queries failed total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_ruler_queries_zero_fetched_series_total:rate5m` | Metrics and stack backend | instance ruler queries zero fetched series total:rate5m | rate | CD | yes/yes |
| `grafanacloud_instance_samples_discarded` | Metrics and stack backend | instance samples discarded | unknown | CD | yes/yes |
| `grafanacloud_instance_samples_discarded_per_second` | Metrics and stack backend | instance samples discarded per second | rate | CD | yes/yes |
| `grafanacloud_instance_samples_per_second` | Metrics and stack backend | instance samples per second | rate | CD | yes/yes |
| `grafanacloud_irm_active_user_count` | IRM | irm active user count | gauge candidate | C | yes/- |
| `grafanacloud_irm_billable_users` | IRM | irm billable users | billing quantity, window unverified | C | yes/- |
| `grafanacloud_irm_overage` | IRM | irm overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_k6_stack_static_ip_billable_usage` | k6 | k6 stack static ip billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_k6_stack_virtual_user_hours_usage` | k6 | k6 stack virtual user hours usage | billing-period cumulative | C | yes/- |
| `grafanacloud_k6_static_ip_overage` | k6 | k6 static ip overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_k6_virtual_user_hours_overage` | k6 | k6 virtual user hours overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_active_streams` | Logs | logs instance active streams | gauge candidate | CD | yes/yes |
| `grafanacloud_logs_instance_adaptivelogs_bytes_dropped_per_second` | Logs | logs instance adaptivelogs bytes dropped per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_adaptivelogs_policy_bytes_dropped_per_second` | Logs | logs instance adaptivelogs policy bytes dropped per second | rate | C | yes/- |
| `grafanacloud_logs_instance_adaptivelogs_policy_lines_dropped_per_second` | Logs | logs instance adaptivelogs policy lines dropped per second | rate | C | yes/- |
| `grafanacloud_logs_instance_attributed_bytes_received_per_second` | Logs | logs instance attributed bytes received per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_attributed_overage` | Logs | logs instance attributed overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_attributed_retention_overage` | Logs | logs instance attributed retention overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_attributed_retention_usage` | Logs | logs instance attributed retention usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_attributed_usage` | Logs | logs instance attributed usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_billable_bytes_received_per_second` | Logs | logs instance billable bytes received per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_bytes_processed_per_second` | Logs | logs instance bytes processed per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_bytes_received_per_second` | Logs | logs instance bytes received per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_cloud_logs_export_exported_bytes` | Logs | logs instance cloud logs export exported bytes | unknown | C | yes/- |
| `grafanacloud_logs_instance_cloud_logs_export_last_synced_file_timestamp` | Logs | logs instance cloud logs export last synced file timestamp | gauge candidate | C | yes/- |
| `grafanacloud_logs_instance_cloud_logs_export_status` | Logs | logs instance cloud logs export status | gauge candidate | C | yes/- |
| `grafanacloud_logs_instance_created_date` | Logs | logs instance created date | gauge candidate | CD | yes/yes |
| `grafanacloud_logs_instance_discarded_bytes_per_second` | Logs | logs instance discarded bytes per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_info` | Logs | logs instance info | gauge candidate | CD | yes/yes |
| `grafanacloud_logs_instance_limits` | Logs | logs instance limits | gauge candidate | CD | yes/yes |
| `grafanacloud_logs_instance_overage` | Logs | logs instance overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_process_overage` | Logs | logs instance process overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_process_usage` | Logs | logs instance process usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_query_bytes:rate1m` | Logs | logs instance query bytes:rate1m | rate | CD | yes/yes |
| `grafanacloud_logs_instance_query_bytes:rate5m` | Logs | logs instance query bytes:rate5m | rate | CD | yes/yes |
| `grafanacloud_logs_instance_query_overage` | Logs | logs instance query overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_retention_overage` | Logs | logs instance retention overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_retention_usage` | Logs | logs instance retention usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_logs_instance_rule_config_last_reload_successful` | Logs | logs instance rule config last reload successful | unknown | CD | yes/yes |
| `grafanacloud_logs_instance_samples_discarded_per_second` | Logs | logs instance samples discarded per second | rate | CD | yes/yes |
| `grafanacloud_logs_instance_usage` | Logs | logs instance usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_oncall_instance_alert_groups_resolution_time_seconds_bucket` | IRM OnCall | oncall instance alert groups resolution time seconds bucket | counter candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_alert_groups_resolution_time_seconds_count` | IRM OnCall | oncall instance alert groups resolution time seconds count | gauge candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_alert_groups_resolution_time_seconds_sum` | IRM OnCall | oncall instance alert groups resolution time seconds sum | counter candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_alert_groups_response_time_seconds_bucket` | IRM OnCall | oncall instance alert groups response time seconds bucket | counter candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_alert_groups_response_time_seconds_count` | IRM OnCall | oncall instance alert groups response time seconds count | gauge candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_alert_groups_response_time_seconds_sum` | IRM OnCall | oncall instance alert groups response time seconds sum | counter candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_alert_groups_total` | IRM OnCall | oncall instance alert groups total | counter candidate | CD | yes/yes |
| `grafanacloud_oncall_instance_user_was_notified_of_alert_groups_total` | IRM OnCall | oncall instance user was notified of alert groups total | counter candidate | CD | yes/yes |
| `grafanacloud_org_agent_o11y_generations_included_usage` | Org contract and billing | org agent o11y generations included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_ai_tokens_active_users` | AI tokens | org ai tokens active users | gauge candidate | C | no/- |
| `grafanacloud_org_ai_tokens_additional_tokens` | AI tokens | org ai tokens additional tokens | unknown | C | no/- |
| `grafanacloud_org_ai_tokens_included_additional_tokens` | AI tokens | org ai tokens included additional tokens | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_ai_tokens_overage` | AI tokens | org ai tokens overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_app_o11y_billable_host_hours` | Application Observability | org app o11y billable host hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_app_o11y_included_host_hours` | Application Observability | org app o11y included host hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_app_o11y_overage` | Application Observability | org app o11y overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_assistant_included_users` | Assistant | org assistant included users | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_assistant_overage` | Assistant | org assistant overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_assistant_users` | Assistant | org assistant users | unknown | C | no/- |
| `grafanacloud_org_billable_users_grafana` | Org contract and billing | org billable users grafana | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_contract_end_date` | Org contract and billing | org contract end date | gauge candidate | C | no/- |
| `grafanacloud_org_contract_start_date` | Org contract and billing | org contract start date | gauge candidate | C | no/- |
| `grafanacloud_org_db_o11y_billable_host_hours` | Org contract and billing | org db o11y billable host hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_db_o11y_included_host_hours` | Org contract and billing | org db o11y included host hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_db_o11y_overage` | Org contract and billing | org db o11y overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_fe_o11y_billable_sessions` | Frontend Observability | org fe o11y billable sessions | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_fe_o11y_included_sessions` | Frontend Observability | org fe o11y included sessions | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_fe_o11y_overage` | Frontend Observability | org fe o11y overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_forecast_months_remaining` | Org contract and billing | org forecast months remaining | unknown | C | no/- |
| `grafanacloud_org_grafana_billable_users` | Grafana core | org grafana billable users | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_grafana_included_users` | Grafana core | org grafana included users | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_grafana_overage` | Grafana core | org grafana overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_grafana_plugin_included_users` | Grafana core | org grafana plugin included users | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_grafana_plugin_users` | Grafana core | org grafana plugin users | unknown | C | no/- |
| `grafanacloud_org_grafana_plugin_users_overage` | Grafana core | org grafana plugin users overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_info` | Org contract and billing | org info | gauge candidate | CD | no/no |
| `grafanacloud_org_infra_o11y_billable_container_hours` | Infrastructure Observability | org infra o11y billable container hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_infra_o11y_billable_host_hours` | Infrastructure Observability | org infra o11y billable host hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_infra_o11y_container_overage` | Infrastructure Observability | org infra o11y container overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_infra_o11y_host_overage` | Infrastructure Observability | org infra o11y host overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_infra_o11y_included_container_hours` | Infrastructure Observability | org infra o11y included container hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_infra_o11y_included_host_hours` | Infrastructure Observability | org infra o11y included host hours | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_irm_included_users` | IRM | org irm included users | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_irm_users` | IRM | org irm users | unknown | C | no/- |
| `grafanacloud_org_irm_users_overage` | IRM | org irm users overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_k6_ip_included_usage` | k6 | org k6 ip included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_k6_ip_overage` | k6 | org k6 ip overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_k6_ip_usage` | k6 | org k6 ip usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_k6_static_ips` | k6 | org k6 static ips | unknown | C | yes/- |
| `grafanacloud_org_k6_virtual_user_hours_included_usage` | k6 | org k6 virtual user hours included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_k6_virtual_user_hours_overage` | k6 | org k6 virtual user hours overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_k6_virtual_user_hours_usage` | k6 | org k6 virtual user hours usage | billing-period cumulative | C | no/- |
| `grafanacloud_org_logs_included_query_to_ingest_ratio` | Logs | org logs included query to ingest ratio | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_included_usage` | Logs | org logs included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_overage` | Logs | org logs overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_process_included_usage` | Logs | org logs process included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_process_overage` | Logs | org logs process overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_process_usage` | Logs | org logs process usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_query_included_usage` | Logs | org logs query included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_retention_included_usage` | Logs | org logs retention included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_retention_overage` | Logs | org logs retention overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_retention_usage` | Logs | org logs retention usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_logs_usage` | Logs | org logs usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_metrics_billable_series` | Org contract and billing | org metrics billable series | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_metrics_included_dpm_per_series` | Org contract and billing | org metrics included dpm per series | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_metrics_included_series` | Org contract and billing | org metrics included series | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_metrics_overage` | Org contract and billing | org metrics overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_included_usage` | Profiles | org profiles included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_overage` | Profiles | org profiles overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_process_included_usage` | Profiles | org profiles process included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_process_overage` | Profiles | org profiles process overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_process_usage` | Profiles | org profiles process usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_retention_included_usage` | Profiles | org profiles retention included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_retention_overage` | Profiles | org profiles retention overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_retention_usage` | Profiles | org profiles retention usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_profiles_usage` | Profiles | org profiles usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_sm_billable_check_executions` | Synthetic Monitoring | org sm billable check executions | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_sm_browser_billable_check_executions` | Synthetic Monitoring | org sm browser billable check executions | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_sm_browser_included_check_executions` | Synthetic Monitoring | org sm browser included check executions | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_sm_browser_overage` | Synthetic Monitoring | org sm browser overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_sm_included_check_executions` | Synthetic Monitoring | org sm included check executions | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_sm_overage` | Synthetic Monitoring | org sm overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_spend_commit_balance_total` | Org contract and billing | org spend commit balance total | billing quantity, window unverified | CD | no/no |
| `grafanacloud_org_spend_commit_credit_total` | Org contract and billing | org spend commit credit total | billing quantity, window unverified | CD | no/no |
| `grafanacloud_org_total_overage` | Org contract and billing | org total overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_included_usage` | Traces | org traces included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_overage` | Traces | org traces overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_process_included_usage` | Traces | org traces process included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_process_overage` | Traces | org traces process overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_process_usage` | Traces | org traces process usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_retention_included_usage` | Traces | org traces retention included usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_retention_overage` | Traces | org traces retention overage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_retention_usage` | Traces | org traces retention usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_org_traces_usage` | Traces | org traces usage | billing quantity, window unverified | C | no/- |
| `grafanacloud_product_activation_status` | Product activation or other | product activation status | gauge candidate | CD | yes/yes |
| `grafanacloud_profiles_instance_billable_bytes_received_per_second` | Profiles | profiles instance billable bytes received per second | rate | D | -/yes |
| `grafanacloud_profiles_instance_bytes_processed_per_second` | Profiles | profiles instance bytes processed per second | rate | D | -/yes |
| `grafanacloud_profiles_instance_bytes_received_per_second_by_stage` | Profiles | profiles instance bytes received per second by stage | rate | D | -/yes |
| `grafanacloud_profiles_instance_created_date` | Profiles | profiles instance created date | gauge candidate | CD | yes/yes |
| `grafanacloud_profiles_instance_info` | Profiles | profiles instance info | gauge candidate | CD | yes/yes |
| `grafanacloud_profiles_instance_overage` | Profiles | profiles instance overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_profiles_instance_process_overage` | Profiles | profiles instance process overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_profiles_instance_process_usage` | Profiles | profiles instance process usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_profiles_instance_retention_overage` | Profiles | profiles instance retention overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_profiles_instance_retention_usage` | Profiles | profiles instance retention usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_profiles_instance_usage` | Profiles | profiles instance usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_profiles_instance_usage_group_bytes_received_per_second` | Profiles | profiles instance usage group bytes received per second | rate | D | -/yes |
| `grafanacloud_profiles_instance_usage_group_estimated_billable_bytes_received_per_second` | Profiles | profiles instance usage group estimated billable bytes received per second | rate | D | -/yes |
| `grafanacloud_sm_billable_check_executions_per_second` | Synthetic Monitoring | sm billable check executions per second | rate | CD | yes/yes |
| `grafanacloud_sm_billable_usage` | Synthetic Monitoring | sm billable usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_sm_browser_overage` | Synthetic Monitoring | sm browser overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_sm_overage` | Synthetic Monitoring | sm overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_adaptivetraces_bytes_dropped_per_second` | Traces | traces instance adaptivetraces bytes dropped per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_bytes_received_per_second` | Traces | traces instance adaptivetraces bytes received per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_discarded_spans_total:rate5m` | Traces | traces instance adaptivetraces discarded spans total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_global_sampled_traces_total:rate5m` | Traces | traces instance adaptivetraces global sampled traces total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_policy_sampled_bytes_total:rate5m` | Traces | traces instance adaptivetraces policy sampled bytes total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_policy_sampled_spans_total:rate5m` | Traces | traces instance adaptivetraces policy sampled spans total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_policy_sampled_traces_total:rate5m` | Traces | traces instance adaptivetraces policy sampled traces total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_adaptivetraces_preprocessing_span_name_cardinality_after_transform` | Traces | traces instance adaptivetraces preprocessing span name cardinality after transform | unknown | D | -/yes |
| `grafanacloud_traces_instance_adaptivetraces_preprocessing_span_name_cardinality_before_transform` | Traces | traces instance adaptivetraces preprocessing span name cardinality before transform | unknown | D | -/yes |
| `grafanacloud_traces_instance_adaptivetraces_preprocessing_spans_transformed_total:rate5m` | Traces | traces instance adaptivetraces preprocessing spans transformed total:rate5m | rate | D | -/yes |
| `grafanacloud_traces_instance_adaptivetraces_spans_received_total:rate5m` | Traces | traces instance adaptivetraces spans received total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_attributed_bytes_received_per_second` | Traces | traces instance attributed bytes received per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_attributed_overage` | Traces | traces instance attributed overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_attributed_usage` | Traces | traces instance attributed usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_bytes_processed_per_second` | Traces | traces instance bytes processed per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_bytes_received_per_second` | Traces | traces instance bytes received per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_created_date` | Traces | traces instance created date | gauge candidate | CD | yes/yes |
| `grafanacloud_traces_instance_discarded_spans_total:rate5m` | Traces | traces instance discarded spans total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_distributor_attributes_truncated_total` | Traces | traces instance distributor attributes truncated total | counter candidate | CD | yes/yes |
| `grafanacloud_traces_instance_info` | Traces | traces instance info | gauge candidate | CD | yes/yes |
| `grafanacloud_traces_instance_ingress_bytes_per_second` | Traces | traces instance ingress bytes per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_limits` | Traces | traces instance limits | gauge candidate | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_active_series_demand_estimate` | Traces | traces instance metrics generator active series demand estimate | gauge candidate | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_discarded_spans_per_second` | Traces | traces instance metrics generator discarded spans per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_label_cardinality_demand_estimate` | Traces | traces instance metrics generator label cardinality demand estimate | unknown | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_post_sanitization_demand_estimate` | Traces | traces instance metrics generator post sanitization demand estimate | unknown | D | -/yes |
| `grafanacloud_traces_instance_metrics_generator_received_spans_per_second` | Traces | traces instance metrics generator received spans per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_series_dropped_per_second` | Traces | traces instance metrics generator series dropped per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_series_limit_percentage_used` | Traces | traces instance metrics generator series limit percentage used | gauge candidate | CD | yes/yes |
| `grafanacloud_traces_instance_metrics_generator_spans_sanitized_per_second` | Traces | traces instance metrics generator spans sanitized per second | rate | D | -/yes |
| `grafanacloud_traces_instance_overage` | Traces | traces instance overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_percentage_complete_traces_flushed` | Traces | traces instance percentage complete traces flushed | unknown | CD | yes/yes |
| `grafanacloud_traces_instance_percentage_traces_with_root_spans_flushed` | Traces | traces instance percentage traces with root spans flushed | unknown | CD | yes/yes |
| `grafanacloud_traces_instance_process_overage` | Traces | traces instance process overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_process_usage` | Traces | traces instance process usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_queries_per_second` | Traces | traces instance queries per second | rate | CD | yes/yes |
| `grafanacloud_traces_instance_retention_overage` | Traces | traces instance retention overage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_retention_usage` | Traces | traces instance retention usage | billing quantity, window unverified | C | yes/- |
| `grafanacloud_traces_instance_spans_more_than_30m_in_past_percent` | Traces | traces instance spans more than 30m in past percent | unknown | CD | yes/yes |
| `grafanacloud_traces_instance_spans_more_than_5m_in_past_percent` | Traces | traces instance spans more than 5m in past percent | unknown | CD | yes/yes |
| `grafanacloud_traces_instance_spans_more_than_60m_in_past_percent` | Traces | traces instance spans more than 60m in past percent | unknown | CD | yes/yes |
| `grafanacloud_traces_instance_spans_received_total:rate5m` | Traces | traces instance spans received total:rate5m | rate | CD | yes/yes |
| `grafanacloud_traces_instance_usage` | Traces | traces instance usage | billing quantity, window unverified | C | yes/- |
