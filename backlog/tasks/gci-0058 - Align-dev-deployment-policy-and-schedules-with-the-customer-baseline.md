---
id: GCI-0058
title: Align dev deployment policy and schedules with the customer baseline
status: To Do
assignee: []
created_date: '2026-10-01 10:05'
labels:
  - deployment
  - parity
dependencies: []
references:
  - LOOP.md
  - RUNBOOK.md
  - consumer/MIGRATION-RUNBOOK.md
priority: medium
type: task
ordinal: 68000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Owner requested this follow-up during loop5 on 2026-10-01 after reviewing the dev and customer scheduled-job timetables. Both deployments use the same generic product but differ in cadence offsets and deployment policy. Establish intentional parity with the customer baseline so dev proves the configuration that will be deployed, while preserving independent staff-org identities/resources and safe staggered execution. Customer identifiers and exact private deployment values must remain in private deployment documentation, not this public task. This request authorizes tracking, not an immediate configuration change during the live rollout.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A fresh comparison of deployed generic source, consumer image provenance, runtime policy, task sizing, deadlines and all five schedules distinguishes intentional isolation differences from unintended drift
- [ ] #2 Dev mirrors the approved customer behavior and policy where safe, with any retained schedule offsets or other differences explicitly justified and documented
- [ ] #3 Org, stack, bucket, secrets, reader credentials, roles and deployment resources remain isolated; no customer identifiers enter public tracked files
- [ ] #4 Any implementation is reviewed and verified through saved plans, live readbacks and proportionate dev runtime proof, with no customer write implied by this task
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
