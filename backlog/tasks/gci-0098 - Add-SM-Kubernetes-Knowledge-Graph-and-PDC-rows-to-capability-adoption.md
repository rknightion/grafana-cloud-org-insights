---
id: GCI-0098
title: 'Add SM, Kubernetes, Knowledge Graph and PDC rows to capability adoption'
status: In Progress
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-06 13:33'
labels:
  - coverage
  - loop13
dependencies: []
priority: medium
type: enhancement
ordinal: 114000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner approved (Rob, 2026-10-06) about five new estate series. Add rows to ADOPTION_CAPABILITIES (collector/pillars/coverage.py) and QUERIES (collector/sources/capability_adoption.py) for grafanacloud_sm_billable_check_executions_per_second, grafanacloud_instance_active_kube_pod_info_series, grafanacloud_asserts_instance_active_entities and grafanacloud_grafana_pdc_connected_agents, extending the gcinsight_coverage_capability_gap kind enum in budget.py. Also correct coverage.py:64, which calls irm_oncall a cumulative counter (it is a gauge).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each new row has a stated population basis and appears in the coverage_capability_adoption view and its call list on the Coverage dashboard; unavailable is absent, never zero
- [ ] #2 budget.py CATALOGUE and BUDGET.md updated; tests/test_budget.py and the dashboard coverage gates pass
- [ ] #3 just check green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root static map proves adoption source/coverage work consumes no missing Loki health helper or contract. Writer-order edge removed after health partial stopped and composed gate completed; retain original criteria and series allowance. Add four bounded capability rows/query/budget dimensions with explicit population basis and absent-not-zero unavailable behavior; correct OnCall gauge wording. Real public source/compose/artifact proof, generated budget, final gate/CR and independent review before integration.
<!-- SECTION:PLAN:END -->
