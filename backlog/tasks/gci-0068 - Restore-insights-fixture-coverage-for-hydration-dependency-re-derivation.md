---
id: GCI-0068
title: Restore insights fixture coverage for hydration dependency re-derivation
status: To Do
assignee: []
created_date: '2026-10-01 14:18'
labels: []
dependencies: []
references:
  - tests/fixtures
  - collector/emit/hydrate.py
priority: low
type: task
ordinal: 78000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 L-cli targeted tests emitted the pre-existing warning that synthetic scans/t2/latest.json lacks an insights payload, so Pillar J dependencies cannot be re-derived from that fixture. The suite passes, but this warning leaves that contract less directly exercised. Investigate the fixture/source contract without copying live identity-bearing data or pinning incidental output.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Synthetic compose fixtures supply the inputs needed to re-derive Pillar J hydration dependencies or explicitly document a justified separate proof
- [ ] #2 The dependency derivation observes the real optional input contract without weakening existing gates
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
