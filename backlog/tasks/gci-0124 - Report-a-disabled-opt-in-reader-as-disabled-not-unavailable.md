---
id: GCI-0124
title: 'Report a disabled opt-in reader as disabled, not unavailable'
status: Done
assignee: []
created_date: '2026-10-07 14:48'
updated_date: '2026-10-07 15:52'
labels:
  - bug
dependencies: []
priority: high
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A default-off opt-in reader that a deployment leaves disabled makes its gather function return an empty payload (scan.py gather_library_panels_inventory and siblings return {} when the reader is not enabled). hydrate.py then records the input as missing with available=False ("latest.json carries no X"), gcinsight_input_available is 0 on every tier, and the input_rule alert (min_over_time(gcinsight_input_available[6h]) < 1) fires indefinitely. Observed read-only on the customer deployment on 2026-10-07 for library_panels_inventory, which that deployment does not enable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A reader disabled by configuration carries a distinct 'disabled' provenance state through gather, scan output and hydration on every tier, is never counted as available, and its dependent views stay withheld (gap-is-absent preserved)
- [x] #2 No input-unavailable alert fires for a disabled reader: either gcinsight_input_available is not emitted for it or the rule excludes it, with a fail-first test showing the old behaviour fired; an enabled reader that fails still alerts
- [x] #3 VIEW_INPUTS re-derivation, the budget catalogue test and the dashboard coverage gate pass unchanged in meaning; just check is green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop15: fail-first reproduction, distinct disabled provenance without availability, suppress disabled alert surface while retaining enabled failure, derived dependency and coverage checks unchanged; guarded review before landing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop15: GCI-0124 (report disabled opt-in readers as disabled, not unavailable) completed after 2 implementation attempts and 1 review-repair round. Exact source 56d5f24f5c6067d135784331c51296d3fcf81f9f, CI 37643734777 required leaves success. Independent security and native publisher/promtool proofs passed; CodeRabbit zero final findings. Composed just check green after root-created external-doc artifact contamination was archived without test weakening: 2351 passed, 2 existing skips, 22735 subtests. Disabled never available, keys persist, enabled failures retain sparse 30-minute alert behavior; derived dependencies/budget/coverage unchanged.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Distinct disabled provenance on every tier, absent availability/age metrics, current enabled policy overrides stale disabled metadata to unavailable, and historical failure alert is gated to latest completed scan samples. Source, real evaluator/publisher, security, CI and composed gate evidence accepted; source rollout remains separate.
<!-- SECTION:FINAL_SUMMARY:END -->
