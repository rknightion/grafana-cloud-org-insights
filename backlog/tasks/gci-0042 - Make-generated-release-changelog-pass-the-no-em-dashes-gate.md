---
id: GCI-0042
title: Make generated release changelog pass the no-em-dashes gate
status: Done
assignee: []
created_date: '2026-09-23 20:00'
updated_date: '2026-09-24 00:20'
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
- [x] #1 Release-please PR changelog has no em or en dashes after a refresh
- [x] #2 PR CI no-em-dashes and ci-success jobs pass at the exact reviewed PR SHA
- [x] #3 The fix preserves normal future changelog generation without modifying historical Git commits
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 2 self-contained App-token workflow fix landed through fa7c2ed. A release-please refresh normalized PR #11 changelog at head 45e48ba, but that head CI was red on literal dash code points in the workflow. Main CI on fa7c2ed passed at run 35930703509. Final feature pushes require one refreshed release PR and green CI at its exact head; no release label yet.

R4 dev promotion failed before scan on a runtime projection digest mismatch and was rolled back. v0.3.0 release is held: do not label PR #11 while the final code is known unproven live. Resume after a new authorized dev promotion repairs the exact projection and meets exit-0/reader-route evidence, then refresh PR and verify CI at its exact head.

Final release-please refresh on main 77c2521 completed maintain-release job in run 35937726067 and advanced PR #11 to exact head 02a3bc14bfb87091d6e4e68af8b0fd7a4bb258f0. CHANGELOG.md at that head has zero em and en dashes. Exact-head CI 35937806114 succeeded: no leaked identifiers, tofu validate, pytest and ci-success all passed. The App-attributed workflow preserves future generation and did not rewrite history. This closes GCI-0042 code/CI ACs; v0.3.0 merge remains separately parked due failed dev rollout.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Generated changelog normalization is automatic and exact-head PR CI is green at 02a3bc1. Release remains unmerged and unlabelled because dev rollout failed.
<!-- SECTION:FINAL_SUMMARY:END -->
