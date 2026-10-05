---
id: GCI-0089
title: >-
  Withhold unqualified usage totals when daily or active-user coverage is
  incomplete
status: In Progress
assignee:
  - '@loop12-root'
created_date: '2026-10-03 12:13'
updated_date: '2026-10-05 14:21'
labels:
  - data-quality
dependencies: []
references:
  - collector/pillars/usage.py
priority: medium
type: bug
ordinal: 99000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop11 focused review of the missing-daily dormancy fix proved two pre-existing usage aggregation gaps explicitly excluded from GCI-0088 (missing daily counts out of dormant findings): daily_total still coerces missing/null daily counts to zero, and a partially missing currentActiveUsers denominator can produce estate stickiness. Real usage.build repro: stack active5/daily2 plus stack missingactive/daily2 publishes stickiness0.8. Initial CodeRabbit major also requested withholding the Daily users summary when daily input is incomplete. Both remain out of loop11 admission; no gate or finding was hidden. Follow-up needs its own bounded scope and acceptance.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Red-first real usage.build reproductions cover missing/null daily input and mixed estates with missing/null active denominators; unqualified totals and ratios are absent or explicitly qualified by measured coverage.
- [ ] #2 Fully measured zero and positive inputs preserve intended behavior; per-stack dormancy and stickiness semantics accepted by GCI-0088 remain unchanged.
- [ ] #3 No unrelated pillar scoring or permission changes; final just check, complete review and exact-SHA CI identify the correction.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Red-first usage.build incomplete daily and active denominator reproductions; withhold unqualified summaries while preserving complete zero/positive and per-stack semantics; review and gate before landing.
<!-- SECTION:PLAN:END -->
