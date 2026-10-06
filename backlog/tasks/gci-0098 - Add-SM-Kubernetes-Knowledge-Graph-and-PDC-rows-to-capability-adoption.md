---
id: GCI-0098
title: 'Add SM, Kubernetes, Knowledge Graph and PDC rows to capability adoption'
status: To Do
assignee: []
created_date: '2026-10-06 10:23'
labels:
  - coverage
  - loop13
dependencies:
  - GCI-0097
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
