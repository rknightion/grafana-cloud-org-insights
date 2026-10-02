---
id: GCI-0071
title: Bound individual AWS observation waits in the ECS task observer
status: In Progress
assignee:
  - '@loop9-root'
created_date: '2026-10-02 00:18'
updated_date: '2026-10-02 09:13'
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
- [ ] #1 An individual describe-tasks or head-object observation cannot hold the observer beyond its explicit bounded wait; a timed-out observation participates in the existing consecutive-failure exit-3 contract
- [ ] #2 Recorded ARN, original run deadline and zero-RunTask adoption remain intact; no new cancellation or retry of an unknown task-launch mutation is introduced
- [ ] #3 Offline process-edge proof with a fake hanging AWS observation fails on the accepted loop8 tool and passes after the change; transient recovery and credential-safe diagnostics remain covered without live AWS calls
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
