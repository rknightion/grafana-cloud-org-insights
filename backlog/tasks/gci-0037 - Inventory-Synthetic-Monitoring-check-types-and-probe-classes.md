---
id: GCI-0037
title: Inventory Synthetic Monitoring check types and probe classes
status: To Do
assignee: []
created_date: '2026-09-23 18:35'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: medium
type: enhancement
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 4 - high value, moderate access and privacy cost. The current usage metric proves execution quantities but not typed check inventory. Resolve the documented SM backend address and a safe read credential after the separate scope decision. Proposed new emitted series: 0; check and probe counts are point-in-time views.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 GET check and probe routes are verified on more than one stack before use
- [ ] #2 Output retains only bounded check type and public/private probe class, not target URLs or scripts
- [ ] #3 Unavailable coverage is absent, not zero
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
