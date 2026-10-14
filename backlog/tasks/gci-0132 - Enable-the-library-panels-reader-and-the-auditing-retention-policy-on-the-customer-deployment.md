---
id: GCI-0132
title: >-
  Enable the library-panels reader and the auditing retention policy on the
  customer deployment
status: In Progress
assignee:
  - '@codex'
created_date: '2026-10-12 09:48'
updated_date: '2026-10-14 11:47'
labels:
  - customer
  - rollout
dependencies: []
priority: medium
ordinal: 169000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner decision D-CUST23 (Rob, 2026-10-12). The customer consumer stays on v0.11.0 source. Add library-panels to the provisioner and scan product reads and set the expected retention policy {kind="auditing"} minimum 120d, both already running on dev. One provisioner run adds only library.panels:read and folders:read on folders:* to the existing reader role (no re-mint), then one saved-plan apply and one T2.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Dev readback shows library-panels and retention-policy views published for every live dev stack before any customer change
- [ ] #2 Customer reader role readback before and after one provisioner run differs only by the two library-panels pairs; no token minted or rotated
- [ ] #3 Customer overlay change limited to the two product-read lists and GCINSIGHT_EXPECTED_RETENTION_POLICY; saved targeted plan applied exactly; final targeted plan reports no changes
- [ ] #4 One customer T2 exits 0 with immutable publication; library-panels and retention-policy views represent every scannable stack or record a reason per stack
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-CUST23 implementable packet: after GCI-0119.15 (prove labelling live on dev) is accepted, fresh STS and dev view/live-inventory readback, customer pre-role/token/SSM witness, exactly one provisioner adding only two folder-scope read pairs with zero mint/rotation, post-role readback, isolated overlay changes to two read lists and auditing 120d expected policy, reviewed saved targeted plan exact apply, exactly one T2 after no active/imminent natural run, adopt ARN on timeout, immutable publication/view evidence and no-change plan. Source stays v0.11.0; no schedule/policy/bucket writes; fix forward only.

2026-10-14 owner replaced the natural 48-hour prerequisite with one successful fresh full-estate dev scan and authorized autonomous fix-forward and manual scans. Resume only after that revised dev proof. Use the actual current released source, never downgrade to the historical v0.11 wording. Preserve durable reader SA/role/token IDs and SSM versions; existing recorded transient Admin repair authority is separate and must be cleaned up. Expected auditing policy assesses 120d, it does not change customer Loki retention.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: zero implementation/live mutation attempts; dependency parked on GCI-0119.15 (prove labelling live on dev), whose historical natural task/memory artifact proof failed. Dev library inventory and policy-status views each publish six rows; policy statuses unreadable, not compliance. Customer untouched. Resume at fresh STS and required dev/live inventory witnesses after prerequisite accepted.

loop23 evidence-boundary clarification: the retained dev view reads show six rows against the latest captured T2 scan population at 2026-10-12T04:37:44Z, not an independent fresh Grafana.com inventory witness at read time. AC #1 remains unchecked. After GCI-0119.15 (prove labelling live on dev) is accepted, resume with fresh inventory and both view readbacks before any customer mutation; current policy statuses are unreadable, never compliance.

2026-10-13 owner explicitly preserved the existing 48-hour natural labelling prerequisite while authorizing other deployments now. Library reader/auditing retention rollout remains dependent, no scope expansion or customer reader/policy mutation from the observer/query-image updates.

2026-10-14 single fresh manual dev prerequisite accepted under owner regrade, preserving explicit execution-sampled memory boundary and original 3-day verifier unproved. Fresh independent dev visible inventory/library/retention row sets match6scannable stacks, AC1proved; unknown retention statuses are not compliance. Customer before-reader snapshot is read-only in progress; no customer apply or reader repair yet.
<!-- SECTION:NOTES:END -->
