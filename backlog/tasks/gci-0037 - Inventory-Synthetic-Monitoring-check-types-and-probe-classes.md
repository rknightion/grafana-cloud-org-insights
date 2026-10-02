---
id: GCI-0037
title: Inventory Synthetic Monitoring check types and probe classes
status: Parked
assignee:
  - '@loop9-root'
created_date: '2026-09-23 18:35'
updated_date: '2026-10-02 09:15'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root records S-SM exception and staff proxy shapes. L-sm implements exact opt-in scopes and minimised counts, offline proofs, gate/review/CI. Root security review and two-stack dev runtime proof.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked at Wave 1 boundary pending GCI-0041 reader scope decision and exact safe read-route verification. No new scope, policy or credential was granted during research.

Loop9 L-sm-a1 contract-blocked without code changes: frozen absent-token deselection permits datasource discovery only after exact held SM UID is known, while permission responses do not encode plugin type. Two identical extra-query roles may point to SM vs unrelated datasource; datasource lookup is required to distinguish but forbidden in unrelated case. Guarded non-baseline candidate discovery would change explicit zero-call predicate and needs owner clarification. No golden, gate, CI, live AC or capability claimed. Root retains exact approved scope record as future policy, not implemented capability.
<!-- SECTION:NOTES:END -->
