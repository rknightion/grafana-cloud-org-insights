---
id: GCI-0071
title: Bound individual AWS observation waits in the ECS task observer
status: Done
assignee:
  - '@loop9-root'
created_date: '2026-10-02 00:18'
updated_date: '2026-10-02 12:07'
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
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
L-obs2 isolated offline observer candidate; root adoption and integrated review. No live AWS proof in lane.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop9 L-obs2-a1 infra retry1 corrected absent checkout; candidate accepted root diff review and copied hash-verified. runtier SHA256 f16b9f2fcc5c69f45970568e40c796f463290f08af2b9f2f71e05344b6ac4ed1; test SHA256 1a061edaf7741f9a665fb28c1f59a9d3a520d07e720278fd399cfa452a65f2f9. Old hanging observation fails exit124 versus expected3; new shellcheck and full fakeAWS process-boundary suite green. Observation-only default5s bound, launch unchanged/unbounded; sameARN/originaldeadline zero-launch adoption. No hosted CI applicable ignored tools; integrated review and live use pending.

Loop9 R-int round1 found MAJOR inherited valid-status-prefix validator hole: STOPPED plus truncated fields falsely passes; STOPPED/0/freeform synthetic credential suffix is printed verbatim, also possible TIMEOUT raw status. Initial local acceptance revoked and AC1/AC3 reopened pending L-obs2-a2 repair and independent round2. Also repair bounded cleanup after killing a timed-out observation so escaped stdout-holder cannot prolong caller wait. No live credential disclosure observed; offline synthetic sentinel only. Prior a1 files hash-archived; root will not deploy with them.

L-obs2-a2 review-repair1 resolved MAJOR safe-rendering defect and bounded post-kill cleanup. New observer5659d1f2f47145c618dd7484513f2119633f80dd7d34946fc7be354fab1ef0e1, test585f1e57da3ab12d6ecc7ec458a4361f23096f63ea1fd5fc0a2946ac2756356c; manifest044e227e09d38add45c5b4a0b77153f06f2b9b22427911a74200d5a2a5f0569d. Three new reproductions failed before fix; final shellcheck/full fakeAWSsuite green. Independent R-int round2 PASS exact hashes, three narrow selectors individually green; initial combined reviewer invocation red without captured cause, disclosed timing limitation not counted uninterrupted green. Escaped descendants may survive but caller wait is bounded; response memory is not bounded. Root adopted copied hashes for live observer. Generic repository DoD exact clean9f2c066 justcheck1685passed/2skipped,8016subtests and hostedCI36991177819 success; that CI does not cover ignored observer, which has separate offline proof. No CodeRabbit/hosted observerCI required.

Live use: accepted a2 observer completed three dev tasks on recordedARNs withoriginaldeadlines, all0 andS3advance; no relaunch. Parent missed required120s T3 descriptor capture (199.38s) despitecomplete immutabledescriptor retained. T2capture14.12s; rootadapter now captures stoppeddescriptor inline immediatelyafteracceptedobserverexit andT1exercise succeeded. This is a parent proceduralmiss, not an observer runtime failure; devacceptance/customerrollout parked ratherthanwaiving timinggate. No realcredential exposure observed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Bounded AWS read observation tool adopted after two implementation attempts and two integrated review rounds. Both normal timeout and escaped-pipe cleanup bounded; malformed responses do not reset failure count; raw stoppedReason never printed; initial RunTask remains outside read fence and adoption never relaunches. Current acceptance binds a2 hashes, not historical a1.
<!-- SECTION:FINAL_SUMMARY:END -->
