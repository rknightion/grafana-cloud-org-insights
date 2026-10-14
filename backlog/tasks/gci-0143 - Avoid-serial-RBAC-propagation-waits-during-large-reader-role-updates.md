---
id: GCI-0143
title: Avoid serial RBAC propagation waits during large reader role updates
status: Parked
assignee: []
created_date: '2026-10-14 12:46'
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
- [ ] #1 A role-only repair of an existing healthy basic-None reader does not hold a transient Admin identity through serial propagation sleeps; credential/role writes remain scoped and recorded.
- [ ] #2 End-of-run verification still proves effective permissions after real propagation; pending, auth failure and unavailable states cannot become success.
- [ ] #3 No working durable token is minted or rotated, existing mint/cleanup/recorded-ID/first-auth-failure boundaries and regression checks remain intact.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
