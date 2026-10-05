---
id: GCI-0090
title: Repair AWS-account and PDC live schema failures before optional-reader rollout
status: Parked
assignee:
  - '@loop12-root'
created_date: '2026-10-03 18:50'
updated_date: '2026-10-05 15:10'
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
- [x] #1 Reproduce each schema failure through its real guarded GET source with a red check derived from minimized non-secret live response shape; preserve fail-closed publication and last-good semantics.
- [ ] #2 Fix only witnessed contracts within approved route/pair scope, retaining fresh inventory-led joins and strict completeness; pass repository gate and independent review.
- [ ] #3 A separately authorized dev rerun proves both readers before any customer rollout; use saved manifests, immutable image identity and unchanged working reader credentials.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop12: 1 implementation attempt,0 review-repair rounds. Bounded PDC metadata repair landed bbb9668dd89b5733d6817b6cfb1fdaaf1d05cb57 with real guarded GET four-shape red-first proofs, complete CodeRabbit zero findings, independent review PASS, clean integrated/composed gates and CI37329484807 success. AWS exact200 data:null on3/5 remains unavailable, never zero. Official CSP3.39.0 UI consumer normalizes null but discards query errors; independent high review rejects that as complete-empty API proof. Needs endpoint-specific authoritative backend contract distinguishing complete empty from unreadable, visibility-filtered or partial. AC2 full repair and AC3 live dev proof not satisfied. Stable0.7.0 release/dev/customer parked on this dependency; no deployment writes. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop12-evidence/R-shape/ and /Users/rob/repos/grafana-cloud-org-insights/codex/loop12-evidence/R-null-frontend/.
<!-- SECTION:NOTES:END -->
