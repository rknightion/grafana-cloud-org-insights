---
id: GCI-0071
title: Bound individual AWS observation waits in the ECS task observer
status: In Progress
assignee:
  - '@loop9-root'
created_date: '2026-10-02 00:18'
updated_date: '2026-10-02 09:34'
labels: []
dependencies: []
references:
  - codex/loop8-tools/runtier.sh
  - codex/loop8-tools/test_runtier.sh
priority: medium
type: task
ordinal: 81000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop8 accepted the exit-3 observer for failed authentication/read responses and proved adoption without relaunch. Independent review also confirmed its polling deadline does not fence a single hung AWS CLI observation: the outer watcher may remain the only wake until its cap. This is a residual operations risk, not an observed live hang in loop8 and not admitted to its closed envelope. Scope observation calls only; an unknown RunTask mutation must be reconciled, never killed and retried as if no task existed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 An individual describe-tasks or head-object observation cannot hold the observer beyond its explicit bounded wait; a timed-out observation participates in the existing consecutive-failure exit-3 contract
- [x] #2 Recorded ARN, original run deadline and zero-RunTask adoption remain intact; no new cancellation or retry of an unknown task-launch mutation is introduced
- [x] #3 Offline process-edge proof with a fake hanging AWS observation fails on the accepted loop8 tool and passes after the change; transient recovery and credential-safe diagnostics remain covered without live AWS calls
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
L-obs2 isolated offline observer candidate; root adoption and integrated review. No live AWS proof in lane.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop9 L-obs2-a1 infra retry1 corrected absent checkout; candidate accepted root diff review and copied hash-verified. runtier SHA256 f16b9f2fcc5c69f45970568e40c796f463290f08af2b9f2f71e05344b6ac4ed1; test SHA256 1a061edaf7741f9a665fb28c1f59a9d3a520d07e720278fd399cfa452a65f2f9. Old hanging observation fails exit124 versus expected3; new shellcheck and full fakeAWS process-boundary suite green. Observation-only default5s bound, launch unchanged/unbounded; sameARN/originaldeadline zero-launch adoption. No hosted CI applicable ignored tools; integrated review and live use pending.
<!-- SECTION:NOTES:END -->
