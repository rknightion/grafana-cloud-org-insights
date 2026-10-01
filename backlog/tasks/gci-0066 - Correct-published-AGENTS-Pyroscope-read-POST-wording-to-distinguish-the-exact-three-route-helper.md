---
id: GCI-0066
title: >-
  Correct published AGENTS Pyroscope read-POST wording to distinguish the exact
  three-route helper
status: To Do
assignee: []
created_date: '2026-10-01 13:51'
labels: []
dependencies: []
references:
  - AGENTS.md
  - collector/sources/dataplane.py
  - collector/sources/signal_inventory.py
priority: medium
type: docs
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 found the published repository AGENTS.md says label_risk.py alone may perform native Pyroscope read POSTs. Existing signal_inventory.py also calls the legacy Connect-RPC helper for LabelValues. Rob approved the helper exact three-route guard while retaining the separate two-route label-risk exception. AGENTS.md comes from an external canonical publisher and must not be hand-edited here; correct that source through its publishing process.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The canonical publisher source distinguishes the exact three helper routes from the dedicated label-risk two-path exception
- [ ] #2 Regenerated AGENTS.md agrees with the implemented boundaries without widening route or live-write authority
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
