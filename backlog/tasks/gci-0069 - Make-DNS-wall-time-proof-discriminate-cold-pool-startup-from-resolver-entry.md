---
id: GCI-0069
title: Make DNS wall-time proof discriminate cold pool startup from resolver entry
status: Done
assignee:
  - '@loop8-root'
created_date: '2026-10-01 14:53'
updated_date: '2026-10-01 21:24'
labels: []
dependencies: []
references:
  - tests/test_netbound.py
  - collector/netbound.py
priority: medium
type: task
ordinal: 79000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 security r2 and root exact gate independently saw unchanged test_netbound resolver tests time out before setting the entered-DNS event. The 0.1s caller budget can be exhausted while the fixed thread pool starts under host contention (observed load180); isolated reruns passed. This is not proof that a blocked DNS read exceeded its caller bound, but it destabilises the required gate and leaves the measured phase ambiguous. Do not relax timeout/assertions or hide a real resource-bound regression.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Offline proofs distinguish pool-start/admission deadline behavior from actually entered blocked DNS with objective phase evidence
- [x] #2 Blocked resolver and caller wall-time contracts remain enforced without weakened assertions or special-case input behavior
- [x] #3 The prior entry-race is reproduced under a controlled local process-edge fixture before the correction and no live network is used
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop8 bounded implementation per frozen packet; worker owns offline reproduction/gate/review and terminal return; root owns tracker reconciliation and integrated acceptance.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop8 L-dns landed 8713714224d80627041c51520df956ce7b0ab472. Exact CI 36927871110 cancelled as superseded, never counted pass; first descendant 50d8e509532e9f229b03bc058fea2a6c3a80ff73 CI 36927879064 success. CodeRabbit complete zero findings covering tests/test_netbound.py. L-dns-a1 red expectation for guarded public exception repaired on new observed evidence in L-dns-a2; no weakened wall-time/resolver/survivor bounds. Root final diff read confirms objective phase separation; reproduction and gate logs copied under codex/loop8-evidence/L-dns.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Distinguished cold-pool admission timeout from entered blocked DNS offline across six public routes, preserving deadlines/resource bounds. 1682 passed, 2 skipped, 8003 subtests on final candidate; green descendant CI 36927879064; no production code change.
<!-- SECTION:FINAL_SUMMARY:END -->
