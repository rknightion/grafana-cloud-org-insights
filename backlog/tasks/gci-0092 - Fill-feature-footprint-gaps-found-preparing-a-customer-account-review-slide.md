---
id: GCI-0092
title: Fill feature-footprint gaps found preparing a customer account-review slide
status: In Progress
assignee: []
created_date: '2026-10-05 09:18'
updated_date: '2026-10-09 13:44'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: medium
type: enhancement
ordinal: 102000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Preparing a customer Grafana Cloud footprint slide (one tile per product: Scaled / Adopting / Opportunity) from the published views, several tiles could not be filled or needed hand-aggregation across views. Each gap below should land as a point-in-time view row (zero new series) unless a trend genuinely justifies a metric under budget.py rules.

Gaps:
1. Agent Observability (AI Observability): nothing collected. doc-0006 lists grafanacloud_org_agent_o11y_generations_included_usage (org billing); need per-stack adoption (stacks sending generations, generation volume over a stated window) from a verified source.
2. Database Observability: doc-0006 lists grafanacloud_instance_active_dbo11y_* but it is not in coverage_capability_adoption. Add a row (stacks with active dbo11y instances, instance count).
3. Application Observability and Kubernetes / Infra Observability: no adoption row or host-hour figure; the slide sourced host hours elsewhere. Add rows from the app_o11y / infra_o11y host-count and host-hour families with the window stated.
4. Adaptive Telemetry as one capability: coverage_capability_adoption has no Adaptive Metrics / Logs / Traces rows. Stacks with applied rules, pending recommendations and removable volume had to be summed by hand from cost, cost_adaptive_logs, cost_adaptive_metric_recommendations and coverage_adaptive_traces_inventory. Also cost_summary publishes null for 'Adaptive rules applied' and the dependent rows while cost.json carries per-stack applied counts on 309 of 310 stacks; confirm whether that null is the intended unknown-propagation (GCI-0067) and, if so, surface the measured-subset figure with its coverage instead of a bare null.
5. Enterprise plugins: usage_plugin_adoption and usage_datasource_inventory do not classify Enterprise datasource plugins, so the count was done against a hand-typed list. Classify from a live source (plugin catalogue signature/plan metadata), never a literal list, and add an Enterprise rollup (stacks, configured datasources by plugin). Query-level usage depth is only available on the few stacks usage-insights covers; state that coverage.
6. Assistant users: ai_summary reports a sum of per-stack active users; the org figure (grafanacloud_org_assistant_users) would de-duplicate and match what account teams quote.
7. Mobile Observability (private preview): record whether any signal exists yet; park if none.

Customer-facing figures that prompted this live in the consumer engagement, not here; do not copy any customer identifier into this repo.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each gap 1-7 is either implemented as a view row with its population basis and window, or recorded in doc-0006 as unobservable with the route or scope that blocks it
- [ ] #2 Agent Observability per-stack adoption is sourced from a verified route or metric, compared against an authorised control before a zero is trusted
- [ ] #3 coverage_capability_adoption includes Adaptive Metrics, Adaptive Logs, Adaptive Traces, Database Observability and Application Observability rows, and the cost_summary null for applied rules is either fixed or documented as intended with the measured-subset figure shown alongside
- [ ] #4 Enterprise plugin classification comes from live plugin metadata, with no literal plugin list in code
- [ ] #5 No new metric is added without a budget.py CATALOGUE entry and a stated trend or alert justification
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop20: implement only gaps 2,3,4,6 in frozen owned files; qualifying existing observations; gate and independent review before landing; live proof remains R-dev10.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop12 children .01-.05 accepted with qualified zero-product-series views and explicit unavailable gaps in the matrix. Parent remains partial: named robk Agent positive-generation control not observed, exact cumulative generation volume and host-hour contracts unresolved; DB reporting markers do not establish units/adoption, Assistant org source empty and default lookback unknown. Do not mark parent AC2 complete or infer zero activity. Library source/publication accepted default-off with no customer grant. Follow-up scope/attempt authorization belongs to a later owner-graded packet.
<!-- SECTION:NOTES:END -->
