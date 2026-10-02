---
id: GCI-0070
title: >-
  Wake the ECS task observer on authentication failures without relaunching its
  recorded task
status: Done
assignee:
  - '@loop8-root'
created_date: '2026-10-01 17:27'
updated_date: '2026-10-02 00:34'
labels: []
dependencies: []
references:
  - codex/loop3-tools/runtier.sh
priority: medium
type: task
ordinal: 80000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 T1 completed successfully in under four minutes, but the existing machine-local ECS observer repeatedly ignored AWS CLI expired-SSO failures and did not observe STOPPED for another 45 minutes. The watcher eventually returned 0, so process success alone hid an authentication observation gap. Root captured the descriptor within seconds of watcher exit and never re-ran the task; no AWS login or credential change was performed. Preserve the task identity and original deadline while making failed observation explicit; this is future operations-tool work, not a collector change.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A failed authentication/read observation becomes a bounded explicit root wake rather than silently repeating until credentials recover
- [x] #2 Recorded task ARN and original deadline survive failure and subsequent adoption; no second RunTask is issued
- [x] #3 Offline process-edge proof exercises an auth failure followed by a STOPPED observation, without live AWS calls or credential output
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop8 bounded implementation per frozen packet; worker owns offline reproduction/gate/review and terminal return; root owns tracker reconciliation and integrated acceptance.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop8 L-obs-a1: old observer auth-failure reproduction timed out as expected; shellcheck and fake-AWS public CLI tests pass. Root read both candidate scripts, accepted conservative stderr redaction and zero-run-task adoption proof, copied and sha256-verified ignored files. runtier.sh 939dce98505a32a1ae5ce063165b0454e4017e92ab63d340bad833633a1ecf45; test_runtier.sh 2b11e98af2ae75fb2418fc69aaf64ff22f2d56c5fce21e1d3ed30db768afef8b. No tracked code or hosted CI; entry exempts just check and CodeRabbit for the ignored observer, with root review instead. Root repository gate passed separately (1676 passed, 2 skipped); skipped tests are not passing evidence. Live behavior remains unproven until rollout use; individual AWS-call hangs retain CLI timeout behavior.

Accepted observer used for five validated one-ARN task runs across dev/customer, each with RunTask full-response validation then adopted observation; STOPPED/containerexit0 and descriptors within2minutes, S3 advancement recorded. No relaunch/timeout/live auth failure occurred. Individual hung-call residual captured separately as GCI-0071 (bound individual AWS observation waits), To Do and not admitted.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Accepted machine-local exit-3 observer preserving recorded ARN/deadline and adoption without relaunch. Offline fake-AWS tests prove expired credentials, transient recovery, adoption to STOPPED, malformed observations and unchanged TIMEOUT. Evidence codex/loop8-evidence/L-obs; candidate hashes recorded in root state.
<!-- SECTION:FINAL_SUMMARY:END -->
