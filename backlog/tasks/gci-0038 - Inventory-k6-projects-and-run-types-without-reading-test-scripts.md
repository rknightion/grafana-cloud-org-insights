---
id: GCI-0038
title: Inventory k6 projects and run types without reading test scripts
status: To Do
assignee: []
created_date: '2026-09-23 18:35'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: medium
type: enhancement
ordinal: 48000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 5 - medium value, moderate access cost. VUh is already visible as a billing-period quantity; projects, cloud/local runs and browser tests require the k6 read API and a verified reader identity. Proposed new emitted series: 0; run and project counts are views.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Read token and exact route are verified without changing existing scopes implicitly
- [ ] #2 Run records distinguish test type and execution mode using documented fields
- [ ] #3 No test script or identity-bearing run body is persisted
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
