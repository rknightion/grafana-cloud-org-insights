---
id: GCI-0122
title: Define per-tab field and enum display ownership contracts
status: To Do
assignee: []
created_date: '2026-10-06 17:50'
labels:
  - dashboards
  - coverage-debt
  - owner-decision
dependencies: []
priority: medium
type: task
ordinal: 157000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Current hardened per-tab checks prove placed query-bearing elements and field selectors against genuine envelopes, not an independently declared tab-specific product coverage contract. Enum selectors may include values while aggregating away their identities. This is disclosed coverage debt, not separately visible enum proof.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner grades tab-specific field/enum ownership and whether distinct enum granularity must survive aggregation, with explicit dispositions for explanatory-only tabs and intentional aggregate headlines.
- [ ] #2 An independent contract and meaningful seeded counterexamples prove each required tab/field/enum display; structural placement or query-name presence alone cannot claim that stronger coverage.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
