---
id: GCI-0093
title: Define and fence future-dated hydrated scan inputs
status: Done
assignee:
  - '@loop13-root'
created_date: '2026-10-05 21:51'
updated_date: '2026-10-06 11:18'
labels:
  - hydration
  - follow-on
dependencies: []
priority: medium
type: bug
ordinal: 109000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Independent loop12 library security review corrected a worker overclaim: collector/emit/hydrate.py rejects missing or too-old ages but admits negative ages; the library tests do not exercise future timestamps. This is pre-existing, not introduced or repaired by the library integration. A future-dated input policy and public-boundary reproduction are needed so future timestamps cannot manufacture freshness. This serves rollout provenance reliability but is outside the accepted schema/null repair packet. Requires an owner-graded follow-up scope and attempt allowance; no loop12 ceiling reset or live deployment is authorized here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Define future-dated owner-input handling and any justified clock-skew tolerance without altering schema-version or own-input hydration rules
- [x] #2 Observe a failing public hydration/compose reproduction, then prove unavailable future input preserves last-good output and honest provenance without weakening exhaustive resource-bounded derivation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop13: public-boundary red-first skew tests; one shared five-minute constant; preserve own-input/schema contracts, CodeRabbit and independent review before land, composed gate.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Park reason is old accepted freshness-policy seam and unresolved clock-skew tolerance, not an exhausted three-cycle budget: contract ceiling is four for all tasks. Root does not reopen or reset accepted GCI-0091 (schema/null hydration repair). Future-age source proof remains unclaimed.

Loop12:0 implementation attempts,0 review-repair rounds; parked owner grading of the older accepted future-age/freshness semantics and clock-skew tolerance. Pre-existing negative-age admission observed by source review, no future-input reproduction or repair claimed. Four-attempt contract corrected; this park is not exhaustion of GCI-0091 (schema/null hydration repair) three cycles.

Owner decision D-FUT13 (Rob, 2026-10-06): a hydrated input stamped up to 5 minutes in the future is admitted as age 0; beyond 5 minutes it is unavailable (view withheld, last-good kept, provenance honest). Red-first test at the public hydrate/compose boundary. Schema-version and own-input hydration rules unchanged.

Loop13: 1 implementation attempt, 0 review-repair rounds. Five-minute shared skew fence accepted and landed 4b4a6b8060e08de78c5049dc2a0c2033079bc4f4; exact archive independent focused proof, red-first public boundary and last-good preservation, CodeRabbit zero findings. Composed just check 2183 passed, 2 skipped, 13348 subtests; CI37453753883 at exact integrated SHA success. Shipped in v0.7.0 source68152d44c96807517385de81bac99c7b617daf58. No live rollout claim.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accepted shared future-stamp policy: through five minutes age0, beyond unavailable with reason and preserved last-good. Gate/CI exact-SHA evidence recorded.
<!-- SECTION:FINAL_SUMMARY:END -->
