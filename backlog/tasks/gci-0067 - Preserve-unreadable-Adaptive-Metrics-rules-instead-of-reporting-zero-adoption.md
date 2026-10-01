---
id: GCI-0067
title: Preserve unreadable Adaptive Metrics rules instead of reporting zero adoption
status: To Do
assignee: []
created_date: '2026-10-01 14:18'
labels: []
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/pillars/cost.py
  - collector/pillars/maturity.py
priority: medium
type: bug
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 read-only M-seg found adaptive_metrics converts an unsuccessful rules response into an empty rule list when recommendations succeed, so rules_applied zero and adopted false can look like measured absence. This is independent of segmented savings coverage; no live failure demonstrated. Source availability and downstream cost/maturity interpretation need an honest unknown state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A failed or malformed applied-rules read is distinguished from a successful empty list
- [ ] #2 Consumers do not present unreadable applied-rule state as measured zero or nonadoption
- [ ] #3 Offline source-to-consumer public-boundary reproduction fails before the correction and proves unknown versus measured empty
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
