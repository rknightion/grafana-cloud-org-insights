---
id: GCI-0058
title: Align dev deployment policy and schedules with the customer baseline
status: Done
assignee:
  - '@loop6-root'
created_date: '2026-10-01 10:05'
updated_date: '2026-10-01 12:59'
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
- [x] #1 A fresh comparison of deployed generic source, consumer image provenance, runtime policy, task sizing, deadlines and all five schedules distinguishes intentional isolation differences from unintended drift
- [x] #2 Dev mirrors the approved customer behavior and policy where safe, with any retained schedule offsets or other differences explicitly justified and documented
- [x] #3 Org, stack, bucket, secrets, reader credentials, roles and deployment resources remain isolated; no customer identifiers enter public tracked files
- [x] #4 Any implementation is reviewed and verified through saved plans, live readbacks and proportionate dev runtime proof, with no customer write implied by this task
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fresh read-only comparison of both deployments and module inputs; classify every difference. Root alone aligns dev drift through saved reviewed plans, preserves isolation, verifies no-change plan and affected-tier runtime. Retain evidence-backed exceptions in private infra comments; no customer writes expected.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop6 R-cmp/R-par accepted live:193 classified difference rows (165 isolation,26 justified,2 deadline drift) in root-private evidence. Only dev T2/T3 deadlines aligned1800->3600; smaller CPU/memory retained with five-stack healthy-run evidence, UTC cadence unchanged and start offsets justified by shared live NAT topology. Nonempty dev retention expectation intentionally tests unreadable/null status; ownership and equivalent wiring exceptions retained in private infra comments. Infra097e0c68ff873fc9cd7a589802bc51d763b8ddef OpenTofu CI36856022636 success. Saved reviewed plan applied once; two definitions and two scheduler targets changed, scheduler IAM actual policy identical. Final targeted plan No changes. Both new revisions ran once, STOPPED0 with S3 advancing; healthy T2/T3 scan durations74.54s/37.61s. Pre/post source/environment/roles/secret metadata/SSM versions/bucket controls unchanged except approved deadline/revision deltas; no schedule suspension, no customer write. Product final integration gate/tracker landing remains pending.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Loop6 root live comparison classified193difference rows and aligned only devT2/T3 caller deadlines to3600seconds. Evidence-backed sizing, schedule offsets, validation policy and ownership exceptions documented in private deployment source. Infra097e0c68 CI36856022636 green; one saved-plan apply, fresh readbacks and final targetedNochanges. Exactlyone task per affectedtier stopped0 and advanced S3 with healthy scans. Org/stack/bucket/secret/reader/role/resource isolation unchanged, schedules remained enabled, customerwrites0. Final product integrated justcheck passed; no release or image change required.
<!-- SECTION:FINAL_SUMMARY:END -->
