---
id: GCI-0090
title: Repair AWS-account and PDC live schema failures before optional-reader rollout
status: To Do
assignee: []
created_date: '2026-10-03 18:50'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 100000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The v0.6.0 dev T2 rollout read five live stacks but cloud_accounts was available on only 2/5 (three invalid_response) and pdc_networks on 0/5 (five invalid_response). The source-owner publication floor refused all S3, Mimir and Loki writes; task exited 1. Dev rolled back to its saved v0.4.4 deployment and old reader selection; only the 61 recorded permission additions were removed, no reader token or SSM version changed. The customer deployment was not upgraded. Root cause is not established; do not infer absence/zero, loosen completeness, change Response.ok globally or widen permissions. This follow-up is outside the closed loop scope.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Reproduce each schema failure through its real guarded GET source with a red check derived from minimized non-secret live response shape; preserve fail-closed publication and last-good semantics.
- [ ] #2 Fix only witnessed contracts within approved route/pair scope, retaining fresh inventory-led joins and strict completeness; pass repository gate and independent review.
- [ ] #3 A separately authorized dev rerun proves both readers before any customer rollout; use saved manifests, immutable image identity and unchanged working reader credentials.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
