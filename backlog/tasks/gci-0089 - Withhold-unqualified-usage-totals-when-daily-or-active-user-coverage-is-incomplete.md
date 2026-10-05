---
id: GCI-0089
title: >-
  Withhold unqualified usage totals when daily or active-user coverage is
  incomplete
status: Done
assignee:
  - '@loop12-root'
created_date: '2026-10-03 12:13'
updated_date: '2026-10-05 14:53'
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
- [x] #1 Red-first real usage.build reproductions cover missing/null daily input and mixed estates with missing/null active denominators; unqualified totals and ratios are absent or explicitly qualified by measured coverage.
- [x] #2 Fully measured zero and positive inputs preserve intended behavior; per-stack dormancy and stickiness semantics accepted by GCI-0088 remain unchanged.
- [x] #3 No unrelated pillar scoring or permission changes; final just check, complete review and exact-SHA CI identify the correction.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Red-first usage.build incomplete daily and active denominator reproductions; withhold unqualified summaries while preserving complete zero/positive and per-stack semantics; review and gate before landing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop12: 1 implementation attempt, 0 review-repair rounds. Landed 642d74468f63ad73e1d80296782f081f37c16ac2; public usage.build reds independently replayed, CodeRabbit complete zero findings, independent review PASS, real-.venv prelanding gate and composed gate green, exact-SHA CI 37327167189 success. Initial DNS gate failure and nonconforming shared symlink proof disclosed and replaced; two skips are not passes.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Incomplete daily or active count coverage now withholds unqualified totals and estate stickiness while preserving fully measured zero/positive and per-stack semantics. Existing no-active fixture changed from null to measured zero because null is unknown, with new missing/null regressions. Verified against landed 642d74468f63ad73e1d80296782f081f37c16ac2 and composed gate; evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop12-evidence/L-usage/.
<!-- SECTION:FINAL_SUMMARY:END -->
