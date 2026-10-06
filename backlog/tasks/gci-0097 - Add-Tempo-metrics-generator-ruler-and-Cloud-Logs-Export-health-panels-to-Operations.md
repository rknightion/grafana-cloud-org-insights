---
id: GCI-0097
title: >-
  Add Tempo metrics-generator, ruler and Cloud Logs Export health panels to
  Operations
status: To Do
assignee: []
created_date: '2026-10-06 10:23'
labels:
  - dashboards
  - operations
  - loop13
dependencies:
  - GCI-0096
priority: medium
type: enhancement
ordinal: 113000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gaps 5, 6 and 14: grafanacloud_traces_instance_metrics_generator_* saturation and drops, Mimir/Loki ruler missed iterations, rule evaluation and reload failures, Alertmanager config reload, and grafanacloud_logs_instance_cloud_logs_export_* status. Percent-versus-ratio trap applies (docs/traps.md).
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Operations gains per-stack panels for each family with metric names from the roster
- [ ] #2 Units are stated as verified or unverified per doc-0006; no ratio is rendered as a percentage without evidence
- [ ] #3 just check green; zero new metric
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
