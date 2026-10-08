---
id: GCI-0125
title: Resolve Synthetic owner-input coverage before deployment acceptance
status: Parked
assignee: []
created_date: '2026-10-07 16:48'
updated_date: '2026-10-08 10:35'
labels:
  - synthetic
  - deployment-blocker
  - owner-decision
dependencies:
  - GCI-0127
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
- [x] #1 Owner-approved disposition resolves each blocker class while preserving unique regex-valid Synthetic uid scope, basic None, no broad query/write grant, no re-mint of working credentials, bounded reads and the publication floor.
- [x] #2 The accepted version and any change to the older-release acceptance or serial rollout prerequisite are explicitly recorded; no immutable release is retagged or accepted by substituting another tier.
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

Owner disposition (Rob, 2026-10-07, loop16 prep): fix the oversized reads forward under GCI-0127 (route-specific Synthetic body bound), then move the customer to the release containing it with no manual runs; Rob checks the overnight natural runs. After the fix 6 of 81 stacks stay unavailable (2 ambiguous, 3 new-stack credential gaps, 1 HTTP 403), inside FAILURE_ABORT_RATIO 0.10. Floor, scope and credentials unchanged.

loop16: GCI-0125 (resolve Synthetic owner-input coverage before deployment acceptance) owner disposition executed via GCI-0127 (route-specific Synthetic body bound), attempts0 for this disposition task. Accepted signed publicv0.8.2 source412ef5cb; dev nativeT2 exit0, Synthetic3applicable/3available+2known-no-datasource. Customer exact source-bound3d1 consumer rollout accepted with312existingbasicNone readers/pairs/tokens/SSM unchanged,3missing+1paused, privacy and8existingactive+routed rules preserved; no manual customer or provisioner run, no scope/floor/remint/datasource edit, no retag. AC3 stays OPEN for owner overnight naturalT2+immutable publication and remaining full dashboard/name proof; collectionmetadata is not fullv2/render/grading. Expected6/81 residual disposition is owner-approved planning evidence, not a new customerT2 observation.

loop17: implementation attempts0 for this read-only disposition; source fix allowance untouched. Natural readback unaccepted. Fresh root baseline at22:30UTC showed0retainedSTOPPED/0RUNNINGcustomerT2, actual enabledschedule03:30UTC, last task-definition R-rel4 consumer3d1. No natural run observed in the available read window. AWSSSO expired22:50UTC; prescribed+30min,+1h,+2h STS eachfailed255, no login or credential repair. No manualreplacement or customerrun. AC3 remainsOPEN. Resume afterauth recovery with exact natural stoppedARN, R-rel4consumer digest, exit0, completeSynthetic report and immutable timestamped version-specificS3 publication tied to task; existing remainingdashboard/name grading not inferred.

loop18: attempts0 for read-only disposition. Natural exact-ARN T2 found from scheduler CloudTrail, revision22 bound to R-rel4consumer3d1; healthy scan_complete duration1685.01s, immutable version-specific publication03:58:51Z, Synthetic73/76 applicable,3unavailable,239known-not-applicable (fresh discovered denominator differs from81 planning). AC3 remainsOPEN: stoppeddescriptorMISSING and no terminalECS event archive discovered, so exit0 unproven. No replacement/manualrun. Resume with exact-ARN archived terminal descriptor/event; never substitute publication for exit proof.
<!-- SECTION:NOTES:END -->
