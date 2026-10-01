---
id: GCI-0059
title: Refresh CLI help and task-role output descriptions against current contracts
status: In Progress
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:45'
updated_date: '2026-10-01 13:51'
labels:
  - documentation
  - operations
dependencies: []
references:
  - scan.py
  - bin/alerts.py
  - bin/dashboards.py
  - terraform/outputs.tf
priority: medium
type: docs
ordinal: 69000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 documentation audit found shipped CLI docstrings and an output description that still teach obsolete behavior after operator docs were corrected. At source fb5803a, scan.py:10 names a legacy credential, bin/alerts.py:9 and bin/dashboards.py:10-11 say scans never touch the Grafana API, bin/alerts.py:23 calls the six-hour tier weekly, and terraform/outputs.tf:47 says the task role has only S3 on three prefixes despite four storage prefixes, rate-card read, SSM and scoped KMS. These files were outside the doc lane ownership; no behavioral change is requested.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 CLI help accurately describes supported credentials, source API reads and tier cadence without deployment identifiers
- [ ] #2 Task-role output description agrees with the actual IAM boundaries, including rate-card, credential-store and KMS reads
- [ ] #3 Changes remain description/comment-only and pass the relevant repository gate
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.
<!-- SECTION:PLAN:END -->
