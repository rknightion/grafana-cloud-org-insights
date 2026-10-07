---
id: GCI-0123
title: Accept intact Infinity metadata queries in persisted dashboard verification
status: Done
assignee: []
created_date: '2026-10-07 03:48'
updated_date: '2026-10-07 04:58'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 158000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop14 dev v0.7.1 publication accepted all11 dashboard writes, but shared persistence verification falsely rejected cost/value because it requires rows for every Infinity selector. Authored optional metadata JSONata selectors and columns survive exactly; four actual installed-backend read queries returned one correct count/boolean frame each. This distinct generic publisher guard bug is not another implementation attempt for GCI-0072 (qualified Adaptive total), and changes none of the excluded enum/runtime-domain/tab coverage debt.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Unchanged ordinary row and metadata coverage queries both pass persistence verification and publish accepted-write/readback boundary, while absent or blank selectors remain rejected.
- [x] #2 Existing backend, explicit-column, datasource, URL, filter, envelope and layout mutation guards stay effective; changed ordinary or metadata selector fails against its authored contract, with fail-first real-helper regression and no panel-name exception.
- [x] #3 Recorded live persisted coverage artifacts agree with independently reconstructed authored query contracts; distinguish structural repair from installed-backend/browser proof and preserve source/release/attempt accounting.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fix shared verifier only: require nonempty authored/actual selectors and exact authored-query preservation instead of universal rows literal; use real helper under neutral element plus existing public publish boundary tests and preserve negative guards. CodeRabbit/guarded review then root stable composed gate. No source view/helper/coverage changes.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop14:1 implementation attempt, independent guarded PASS, CodeRabbit minor fixed/delta0 findings;13 public-boundary tests/15 subtests plus14 independent mutation negatives. Source/helper/coverage algorithms untouched; no reset of GCI-0072 (qualified Adaptive total) ceiling. Stable e6d8717 fullgate+CI37572599149 green; actual4 installed-backend metadata queries and exact immutable-source authored cost/value readbacks proved; no browser claim.
<!-- SECTION:NOTES:END -->
