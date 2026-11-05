---
id: GCI-0146
title: Provisioner treats a successful non-201 Admin SA create as failure
status: To Do
assignee: []
created_date: '2026-11-05T20:42:00Z'
labels:
  - provisioner
  - bug
dependencies: []
ordinal: 184000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
On the robknight dev estate, new staff stack pulumireflab2 has failed provisioning on every daily run with admin_sa_failed. bin/provision.py repair() requires status == 201 from POST /instances/{slug}/api/serviceaccounts, but the logged detail is the created gcinsight-insights-provisioner SA body (ids 24 then 25), so the create succeeds with another status (probably 200). The id is not ledger-recorded on that path; the exact-name sweep removes it next run, so it does not accumulate, but the stack never gets a reader token. Effect: dev T2 on v0.15.4 (2026-11-05) refused all writes at the 10% floor (1/8 stacks no_credential). Witness the actual status before fixing; accept only a verified success shape and record the id before returning.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Actual create status for the failing stack is witnessed and recorded
- [ ] #2 repair() records and uses a created Admin SA for every verified success status, and refuses others
- [ ] #3 A test covers a 200-with-SA-body create
- [ ] #4 pulumireflab2 provisions on dev and dev T2 publishes
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
