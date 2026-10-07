---
id: GCI-0125
title: Resolve Synthetic owner-input coverage before deployment acceptance
status: Parked
assignee: []
created_date: '2026-10-07 16:48'
updated_date: '2026-10-07 16:48'
labels:
  - synthetic
  - deployment-blocker
  - owner-decision
dependencies: []
references:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop15-evidence/R-cust/synthetic-failure-traces.json
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/codex/loop15-evidence/R-cust/synthetic-fresh-diagnosis-private.json
priority: high
type: task
ordinal: 160000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A full native T2 on the held release refused every publication because Synthetic was available on 72 of 81 eligible stacks (88.9%). Fresh GET-only reproduction matched it: 2 ambiguous datasource sets, 3 missing newly discovered credentials, 3 native guarded-body-limit failures (2 discovery lists and 1 check list), and 1 check-list HTTP403. The native cap is 2 MiB; both queryable failing cases still have the uniquely discovered uid-scoped query pair and unchanged parameter versions. Unknown must remain unknown, never zero or healthy. This blocks acceptance of the older immutable release and therefore the frozen serial dev/next-customer rollout order. No floor, reader policy, foreign datasource, token or scope was changed. Existing project monitor rules were already active and routed; their current input alerts predate the manual chain.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner-approved disposition resolves each blocker class while preserving unique regex-valid Synthetic uid scope, basic None, no broad query/write grant, no re-mint of working credentials, bounded reads and the publication floor.
- [ ] #2 The accepted version and any change to the older-release acceptance or serial rollout prerequisite are explicitly recorded; no immutable release is retagged or accepted by substituting another tier.
- [ ] #3 A subsequent full native T2 exits zero and its immutable timestamped publication is linked to the exact stopped task; reader, identity, privacy, remaining dashboard/name proof and intended alert state are verified.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop15: GCI-0125 (resolve Synthetic owner-input coverage before deployment acceptance) parked owner; implementation attempts 0, review-repair rounds 0. Read-only diagnosis is complete and the older deployment acceptance is negative. Recommend an explicitly approved temporary Synthetic-query deselection with the legacy Synthetic token/pairs preserved, or remediate the unavailable product configuration under a fresh grant; no choice was made unattended.
<!-- SECTION:NOTES:END -->
