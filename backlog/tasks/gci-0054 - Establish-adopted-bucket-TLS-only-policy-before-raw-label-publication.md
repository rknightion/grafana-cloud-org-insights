---
id: GCI-0054
title: Establish adopted-bucket TLS-only policy before raw-label publication
status: Parked
assignee: []
created_date: '2026-09-30 23:42'
labels:
  - retention
  - validation
dependencies: []
priority: high
type: task
ordinal: 64000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A fresh loop4 read of an adopted deployment bucket returned NoSuchBucketPolicy. Enabled versioning, default encryption, public access blocks and the separately granted additive raw-view lifecycle rule do not establish a TLS-deny policy. The loop parked deployment before new raw-label publication because its grant covered one lifecycle write, not a bucket-policy write. No deployment identifiers belong in this task; the exact environment and readback are retained only in the private operations/evidence record. Resume after explicit owner authorization for the policy change, or after an owner-installed policy is independently read back. Do not infer broader adopted-resource write authority.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Explicit owner authority for the policy write is recorded separately from lifecycle or rollout grants
- [ ] #2 Fresh effective bucket policy denies non-TLS access on the bucket and object resources, with unrelated policy statements preserved
- [ ] #3 Versioning, encryption, public-access controls and views-only reader access remain correct and are independently witnessed before raw-label publication
- [ ] #4 The blocked rollout resumes only from its recorded image/module/manifest and task state, with no duplicate live task or credential mint
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
