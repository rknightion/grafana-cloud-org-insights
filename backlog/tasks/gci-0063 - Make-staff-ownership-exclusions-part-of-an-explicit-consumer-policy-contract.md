---
id: GCI-0063
title: Make staff ownership exclusions part of an explicit consumer policy contract
status: To Do
assignee: []
created_date: '2026-10-01 11:57'
labels:
  - configuration
  - ownership
dependencies: []
references:
  - collector/pillars/maturity.py
  - collector/identity.py
  - docs/configuration.md
priority: medium
type: task
ordinal: 73000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 reference audit found collector/pillars/maturity.py:83-92 reads GCINSIGHT_STAFF_LOGINS for vendor or partner ownership exclusions, but collector/identity.py:20-29 omits it from SCAN_ENV and immutable consumer projections. Operator docs now disclose that deployments cannot rely on this as a projected policy. The follow-up must decide and document whether exclusions are a supported immutable consumer policy or explicitly retired; the loop made neither product choice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Supported staff-exclusion policy and its ownership are explicitly decided and documented
- [ ] #2 If supported, a manifest-selected exclusion reaches the deployed collector and projection validation detects drift; if retired, no advertised configuration silently has no effect
- [ ] #3 Owner attribution and identity minimization are proved on synthetic non-customer fixtures, with no live identifiers committed
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
