---
id: GCI-0121
title: Declare runtime metric label domains independently of capacity planning
status: Done
assignee: []
created_date: '2026-10-06 17:49'
updated_date: '2026-10-07 17:56'
labels:
  - dashboards
  - coverage-debt
  - owner-decision
dependencies: []
priority: medium
type: task
ordinal: 156000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The new coverage inventory exposes 40 domain declarations whose catalogue values are capacities, not exhaustive vocabularies. Fixture observations cannot certify unseen enum values. Distinguish fixed runtime enums, live-discovered stack/region domains and intentional headroom/version reserves without configuring an estate roster or manufacturing synthetic complete coverage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An independently sourced contract identifies each incomplete domain as fixed runtime vocabulary, discovery-backed domain or reserve, with source witnesses and bounded combinations; unknown remains explicit until proved.
- [x] #2 Coverage derives obligations from that contract rather than capacity numbers or fixture self-agreement; newly introduced unsupported values fail and planning headroom is not falsely reported as runtime data.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop15: identify all 40 incomplete domains from real producer contracts as fixed enums, discovery-backed domains or explicit reserves; preserve unknowns, estate discovery and capacity ceilings. Derive coverage obligations from independently witnessed vocabularies, demonstrate unsupported-value seeds fail, preserve prior negative rendering/reserve tests; final just check, completed CodeRabbit, independent review and exact-SHA CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop15: GCI-0121 (declare runtime metric label domains independently of capacity planning) completed at e260baf30c8c5fb642e391652b10e4e2be39b37b, exact CI 37661072822 and composed just check green: 2374 passed, 2 existing skips, 23163 subtests. Three implementation cycles and one unchanged DNS infrastructure gate retry; worker continued the third cycle without prescribed root-rescue handoff, recorded as route deviation rather than reset/relabeling. Independent review proves unchanged 28 invalid-pair seeds after trivial resource-safe test-generator repair, unchanged planning/catalogue/ten reserves, and exact committed targeted checks. CodeRabbit zero across seven files before that trivial test-only repair; no runtime delta afterward. Ownership amendment added minimal dispatched-skip rendering and its artifact test; frozen goal file was not edited. Three domains remain explicitly UNKNOWN, so no exhaustive coverage/conformance or publisher enforcement claim; GCI-0126 (close bounded-label proof for open Assistant and scan-failure domains) is the parked follow-up.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Separated independently sourced runtime domain contracts from capacity planning and fixture observations. All 40 incomplete declarations classified as 37 fixed/current and three honest UNKNOWNs; fixed unsupported values and relations fail, nine unscored and four dispatched skip pairs derive obligations, fresh estate discovery remains authoritative, headroom/version slots are not fictitious runtime values. Minimal skipped-stack consumer now separates tier/reason 36-hour endpoint peaks with gap-is-absent qualifiers. Exact-SHA review, CI and composed gate accepted; browser/live and publisher enforcement remain unverified.
<!-- SECTION:FINAL_SUMMARY:END -->
