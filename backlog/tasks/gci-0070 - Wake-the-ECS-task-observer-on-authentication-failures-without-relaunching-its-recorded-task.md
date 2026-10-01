---
id: GCI-0070
title: >-
  Wake the ECS task observer on authentication failures without relaunching its
  recorded task
status: To Do
assignee: []
created_date: '2026-10-01 17:27'
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
- [ ] #1 A failed authentication/read observation becomes a bounded explicit root wake rather than silently repeating until credentials recover
- [ ] #2 Recorded task ARN and original deadline survive failure and subsequent adoption; no second RunTask is issued
- [ ] #3 Offline process-edge proof exercises an auth failure followed by a STOPPED observation, without live AWS calls or credential output
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
