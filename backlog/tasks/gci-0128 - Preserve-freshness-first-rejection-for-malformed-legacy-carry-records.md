---
id: GCI-0128
title: Preserve freshness-first rejection for malformed legacy carry records
status: In Progress
assignee: []
created_date: '2026-10-07 23:55'
updated_date: '2026-10-08 10:13'
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
- [ ] #1 Expired or rejected carry state with malformed Assistant labels cannot interrupt an otherwise healthy T1 publication
- [ ] #2 Fresh supported carry still deduplicates projected live identities without double-counting and leaves loaded state unchanged
- [ ] #3 A fail-first real T1/publication reproduction covers the malformed expired-state boundary and distinguishes supported from corrupt state
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop18: fail-first real T1 malformed expired-state reproduction, freshness-first fix, supported dedup and immutability checks, independent review and exact-SHA gate.
<!-- SECTION:PLAN:END -->
