---
id: GCI-0042
title: Make generated release changelog pass the no-em-dashes gate
status: Parked
assignee: []
created_date: '2026-09-23 20:00'
updated_date: '2026-09-24 00:16'
labels: []
dependencies: []
references:
  - >-
    https://github.com/rknightion/grafana-cloud-org-insights/actions/runs/35911955198
priority: high
type: bug
ordinal: 52000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The automated release-please PR #11 for 0.3.0 fails CI although main is green. CI run 35911955198 failed only the no-em-dashes leg: generated CHANGELOG.md lines 54, 55 and 101 copied old backlog commit subjects containing em dashes. The release cannot merge until the generated changelog and its next refresh satisfy the existing gate. This is outside Wave 1 feature and dev-rollout scope; do not rewrite historical commits or weaken the shipped-text gate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Release-please PR changelog has no em or en dashes after a refresh
- [ ] #2 PR CI no-em-dashes and ci-success jobs pass at the exact reviewed PR SHA
- [ ] #3 The fix preserves normal future changelog generation without modifying historical Git commits
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 2 self-contained App-token workflow fix landed through fa7c2ed. A release-please refresh normalized PR #11 changelog at head 45e48ba, but that head CI was red on literal dash code points in the workflow. Main CI on fa7c2ed passed at run 35930703509. Final feature pushes require one refreshed release PR and green CI at its exact head; no release label yet.

R4 dev promotion failed before scan on a runtime projection digest mismatch and was rolled back. v0.3.0 release is held: do not label PR #11 while the final code is known unproven live. Resume after a new authorized dev promotion repairs the exact projection and meets exit-0/reader-route evidence, then refresh PR and verify CI at its exact head.
<!-- SECTION:NOTES:END -->
