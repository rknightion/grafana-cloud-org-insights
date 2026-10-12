---
id: GCI-0130
title: >-
  Plan migrating the customer deployment off adopted identity onto the canonical
  identity
status: Done
assignee:
  - '@loop24-root'
created_date: '2026-10-08 18:57'
updated_date: '2026-10-12 22:40'
labels:
  - consumer
  - handover
  - owner-decision
dependencies: []
priority: medium
ordinal: 167000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision 2026-10-08 (Rob): plan a full migration before handover. Adopted identity still in the customer consumer: metric prefix, Loki job, Grafana reader role name/display/group (present on every stack), reader/admin service-account and token names containing the lab owner token, SSM per-stack token path, the three custom secret key names, adopted alert rule uids/group and folder. Each move has live cost: series history split under a new metric prefix (carry-forward cannot rescue), new roles and reassignment on every stack with the old role orphaned unless pruned by recorded id, re-mint of every per-stack token (a repair must not re-mint a working credential, so this needs its own explicit owner grant), alert routing re-established. Planning only: produce an ordered, reversible-by-fix-forward plan with per-step live witnesses and owner grants; no live change under this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Plan document lists each adopted identity item, its migration step, live blast radius, required owner grant and witness
- [x] #2 Plan reviewed adversarially and corrected
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop24 planning delivered at /Users/rob/repos/grafana-cloud-org-insights/codex/scratch/loop23-gci0130-plan.md. Ordered baseline/holds, unchanged-token secret alias and SSM copies, canonical roles, separately granted reader replacement, shared path/runtime cutover, paused folder/alert staging, namespace history split, explicit routing, exact-ID Admin-last retirement and restoration. Deployment values remain unknown; later discovery, tooling and each mutation need fresh owner grants. Plan acceptance is not customer execution authority.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop24 independent reviewer PASS at document SHA2569102090cd45a7d92f02f151a840220e4060655a52d7d65aeec6012eac533f305, source main da40892016c603714c42b6546bf4d3b12c72316d. Root reconciled output-path defect before review; no substantive blocker/correction found. Non-identifying summary only in tracker, plan remains gitignored. Attempts: 0 product implementation, one planning draft,0 review-repair. No AWS/customer/source/identity discovery, token change, CodeRabbit or runtime gates (planning-only exemption). Review /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/identity-plan/review.md. Done held until root reviewed publication/composed gate.

loop24: zero product implementation attempts, one planning draft,0 review-repair; Done planning-only after exact reviewed artifact, published non-identifying summary, composed clean and hosted exact CI success. Every live step needs a later fresh owner grant.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Planning completed at /Users/rob/repos/grafana-cloud-org-insights/codex/scratch/loop23-gci0130-plan.md, exact SHA2569102090cd45a7d92f02f151a840220e4060655a52d7d65aeec6012eac533f305. Independent adversarial reviewer PASS with no safety corrections; root corrected output binding before review. Each adopted identity item has ordered steps, blast radius, separate future owner grants and fresh ID-bound witnesses. No customer values discovered, live migration, credential change or execution approval. Non-identifying tracker summary published under1addf94c54aea8e6d1b80cfc992289a302a0a55a, composed gate clean and required CI38317158771 success. Legacy runtime DoD commands not run locally for planning-only goal.
<!-- SECTION:FINAL_SUMMARY:END -->
