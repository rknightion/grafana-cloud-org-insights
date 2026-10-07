---
id: GCI-0121
title: Declare runtime metric label domains independently of capacity planning
status: In Progress
assignee: []
created_date: '2026-10-06 17:49'
updated_date: '2026-10-07 16:53'
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
- [ ] #1 An independently sourced contract identifies each incomplete domain as fixed runtime vocabulary, discovery-backed domain or reserve, with source witnesses and bounded combinations; unknown remains explicit until proved.
- [ ] #2 Coverage derives obligations from that contract rather than capacity numbers or fixture self-agreement; newly introduced unsupported values fail and planning headroom is not falsely reported as runtime data.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop15: identify all 40 incomplete domains from real producer contracts as fixed enums, discovery-backed domains or explicit reserves; preserve unknowns, estate discovery and capacity ceilings. Derive coverage obligations from independently witnessed vocabularies, demonstrate unsupported-value seeds fail, preserve prior negative rendering/reserve tests; final just check, completed CodeRabbit, independent review and exact-SHA CI.
<!-- SECTION:PLAN:END -->
