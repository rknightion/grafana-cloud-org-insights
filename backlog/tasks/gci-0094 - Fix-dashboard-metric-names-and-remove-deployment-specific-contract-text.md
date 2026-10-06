---
id: GCI-0094
title: Fix dashboard metric names and remove deployment-specific contract text
status: To Do
assignee: []
created_date: '2026-10-06 10:23'
labels:
  - dashboards
  - loop13
dependencies: []
priority: high
type: bug
ordinal: 110000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment found: bin/dashboards.py:340-342 and tests/test_dashboards.py:959-961 query grafanacloud_instance_app_o11y_host_count_v2/_v3 while the live roster (doc-0006:170-171) has grafanacloud_instance_app_o11y_host_v2_count/_v3_count; collector/ratecard.py:142 cites grafanacloud_instance_assistant_active_users where the roster has grafanacloud_assistant_active_users; the generic Commercial dashboard hard-codes one deployment's contract term (bin/dashboards.py:4202, 4215, 4315 and measured figures in comments near 371-399, 4162) although CONTRACT_START/END are queried live.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each corrected metric name is confirmed present in the doc-0006 roster or a loop13 live name read; a test fails on the old name and passes on the new
- [ ] #2 No deployment-specific contract date, figure or measured value remains in dashboard text or comments; descriptions refer to the live CONTRACT_START/END queries
- [ ] #3 just check green; no new metric
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
