---
id: GCI-0088
title: Keep missing daily user counts out of dormant-stack findings
status: Parked
assignee: []
created_date: '2026-10-02 22:02'
labels:
  - data-quality
dependencies: []
references:
  - collector/pillars/usage.py
priority: medium
type: bug
ordinal: 98000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Independent loop10 documentation review reproduced usage.build with currentActiveUsers5 and dailyUserCnt null: usage_dormant_stacks reports daily0/stickiness0. Inventory missing/null daily counts are coerced to0, so unknown can look dormant. Source behavior predates this docs change. Correct current documentation to disclose it; this source follow-up is outside the frozen implementation envelope and NOT admitted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Real usage.build reproduction for missing/null daily counts is observed failing before correction; unavailable daily data is not emitted as measured dormancy.
- [ ] #2 Known positive daily activity and known zero daily activity keep their intended behavior; missing active-user counts remain distinct.
- [ ] #3 No unrelated scoring/metric/provenance changes; public-boundary proof, final just check, complete review and exact-SHA CI identify the delivered correction.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
