---
id: GCI-0094
title: Fix dashboard metric names and remove deployment-specific contract text
status: Done
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-06 11:55'
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
- [x] #1 Each corrected metric name is confirmed present in the doc-0006 roster or a loop13 live name read; a test fails on the old name and passes on the new
- [x] #2 No deployment-specific contract date, figure or measured value remains in dashboard text or comments; descriptions refer to the live CONTRACT_START/END queries
- [x] #3 just check green; no new metric
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
After accepted v0.7.0 readback: isolated exact-name/text candidate, red-first actual assembled artifact regression, gate and CodeRabbit once, root independent review then integration and exact-SHA CI/composed gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13: 1 implementation attempt, 1 trivial review wording correction cycle, no remaining findings. Candidate223257a63416307e7f5c4a735539a5e8f92b7f10 accepted/landed with independent immutable artifact review PASS; red-first14failed, CodeRabbit complete four-file coverage and minor four-line wording fixed. Final and composed just check2188passed2skipped13364subtests; exactSHA CI37458656533 all required leaves success. CLI builds all eleven artifacts; only two App O11y query spellings changed, generic text removed deployment literals. Customer-only name list in durable return remains for dependency-blocked readback, not current customer proof.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Corrected witnessed metric spellings and removed fixed deployment contract assertions while keeping existing formulas, units and live contract queries.
<!-- SECTION:FINAL_SUMMARY:END -->
