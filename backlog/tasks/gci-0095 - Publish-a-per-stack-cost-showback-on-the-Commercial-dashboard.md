---
id: GCI-0095
title: Publish a per-stack cost showback on the Commercial dashboard
status: To Do
assignee: []
created_date: '2026-10-06 10:23'
updated_date: '2026-10-06 10:23'
labels:
  - dashboards
  - cost
  - loop13
dependencies:
  - GCI-0094
priority: high
type: enhancement
ordinal: 111000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision D-SHOW13 (Rob, 2026-10-06, 'Full showback'): lift SPEC.md's exclusion of a per-stack showback. Build per-stack cost from grafanacloud-usage per-stack billable and overage families (metrics, logs, traces, profiles, Grafana users and plugins, App/Frontend O11y, infra hosts/containers, SM, k6, IRM; names from the doc-0006 roster), joined to slug via grafanacloud_grafana_instance_info (docs/traps.md). Panels only, zero new series.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A showback tab gives per-stack USD per billing line, a per-stack total and top-N stacks overall and per line, each panel naming its metric and carrying the derived-currency caveat
- [ ] #2 A reconciliation panel shows per-stack sums against grafanacloud_org_total_overage per line and states a mismatch rather than hiding it; a line with no per-stack source is shown as unattributed, never zero
- [ ] #3 SPEC.md out-of-scope list updated to admit the per-stack showback; just check green; zero new metric
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
