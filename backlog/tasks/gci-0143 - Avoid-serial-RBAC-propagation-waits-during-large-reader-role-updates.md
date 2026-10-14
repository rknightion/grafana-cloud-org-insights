---
id: GCI-0143
title: Avoid serial RBAC propagation waits during large reader role updates
status: Done
assignee:
  - '@codex'
created_date: '2026-10-14 12:46'
updated_date: '2026-10-14 20:20'
labels: []
dependencies: []
priority: medium
type: enhancement
ordinal: 181000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The 316-stack customer library rollout spends the 5/15/30-second per-stack reader verification backoff after many successful role patches. The existing provisioner already performs a final verification pass after a minimum five-minute propagation age, so serial waits can make a scoped role update take hours. Preserve the currently running original task; this task is future optimization, not permission to interrupt or replace it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A role-only repair of an existing healthy basic-None reader does not hold a transient Admin identity through serial propagation sleeps; credential/role writes remain scoped and recorded.
- [x] #2 End-of-run verification still proves effective permissions after real propagation; pending, auth failure and unavailable states cannot become success.
- [x] #3 No working durable token is minted or rotated, existing mint/cleanup/recorded-ID/first-auth-failure boundaries and regression checks remain intact.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
2026-10-14 corrected independent plan accepted: narrow opt-in role-only deferral binds stored sa_id to listed reader, explicit basic-role None and pre-existing role proof; recorded Admin cleanup False/exception blocks pending; only >=300s final effective-token verification converts to success. Preserve synchronous nonqualifying paths, no durable mint/rotation. Worker owns bin/provision.py, collector/provision.py constant and tests/test_provision_io.py. Root owns tracker/review/gate/release.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner 2026-10-14 retains reader-update optimization. Root authorized implementation; separate worker owns bounded source/test changes, no live role repair or credential writes during development.

Corrected plan independently reviewed; original worker prepared plan only and is idle. Root took implementation ownership of bin/provision.py, collector/provision.py constant and tests/test_provision_io.py. Fast path binds existing stored/live SA identity and explicit basicNone, checks pre-existing exact role UID, returns verification_pending only after recorded Admin cleanup, and requires bound final effective-token verification after300s. CleanupFalse/exception now fails normal repair results too. No live role/credential writes. New direct and real-main event-order boundary tests prove no serial repair waits, allthreecleanups precede shared300s wait, and no durable mint; old real-main behavior fails these tests. Focused17tests/7subtests pass.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented healthy-existing-reader role batching with exact stored/live SA and pre-existing role binding; no durable credential mint/rotation. Recorded transient Admin cleanup precedes shared propagation wait and any cleanup failure refuses success. Final effective-token verification after>=300s alone changes pending toOK. Real-main three-stack event-order check fails prior source for premature sleep and passes corrected source;138focused regressions/18subtests; final justcheck2807tests/27938subtests/2existing skips/45Tofu/current+originidentifierhistory/noemdashallpass. CodeRabbit finalreview COMPLETE0 across all5files. Deployment of this release candidate remains campaign work; no new live mass-repair performance measurement claimed.
<!-- SECTION:FINAL_SUMMARY:END -->
