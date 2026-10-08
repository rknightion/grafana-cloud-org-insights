---
id: GCI-0128
title: Preserve freshness-first rejection for malformed legacy carry records
status: Done
assignee: []
created_date: '2026-10-07 23:55'
updated_date: '2026-10-08 11:02'
labels: []
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop17-evidence/L-domains/V-domains-delta-boundaries.log
priority: low
type: bug
ordinal: 164000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
loop17 independent review found a minor robustness regression outside the supported-state bounded-label proof: T1 projects legacy metric payloads before carry freshness validation. An expired Assistant metric missing category raises KeyError instead of being discarded. Supported stale/future/invalid-timestamp records and all current schema records still behave correctly. No live occurrence observed. Root deliberately retained this minor residual in the reviewed bounded-projection candidate instead of widening its accepted scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Expired or rejected carry state with malformed Assistant labels cannot interrupt an otherwise healthy T1 publication
- [x] #2 Fresh supported carry still deduplicates projected live identities without double-counting and leaves loaded state unchanged
- [x] #3 A fail-first real T1/publication reproduction covers the malformed expired-state boundary and distinguishes supported from corrupt state
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop18: fail-first real T1 malformed expired-state reproduction, freshness-first fix, supported dedup and immutability checks, independent review and exact-SHA gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop18: implementation attempts1, review-repair rounds0. Real T1/publication fail-first12 malformed rejected-state cases; repaired6test classpasses; supported projected carry remains7not14 and loadedstateimmutable. Independent exactpatch reviewPASS and CodeRabbitcomplete0findings. Landed d60ed418144d47ba5b965724e563f79120c187cf (only2ownedfiles), gate0 and CI37765227990 requiredleaves success. Root integrated13a884e741703c7b0968f2353174876845a0fbf2 composed justcheck0 (2428passed,2skipped,23189subtests) and CI37765790586 success. Freshcorruptpayload outside supportedcontract remains intentionally unnormalized.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Freshness rejection now precedes legacy payload projection. Real T1/native remote_write reproduction distinguishes rejected malformed state from fresh supported carry; independently reviewed exact patch landed, exact CI and composed gate green.
<!-- SECTION:FINAL_SUMMARY:END -->
