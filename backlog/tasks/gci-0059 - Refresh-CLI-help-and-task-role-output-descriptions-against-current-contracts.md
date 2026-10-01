---
id: GCI-0059
title: Refresh CLI help and task-role output descriptions against current contracts
status: Done
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:45'
updated_date: '2026-10-01 14:18'
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
- [x] #1 CLI help accurately describes supported credentials, source API reads and tier cadence without deployment identifiers
- [x] #2 Task-role output description agrees with the actual IAM boundaries, including rate-card, credential-store and KMS reads
- [x] #3 Changes remain description/comment-only and pass the relevant repository gate
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
CLI help names supported read/write/build credentials and SSM source readers, source API reads and module-default hourly/daily/six-hourly/daily cadence; task-role output matches four storage prefixes, exact rate-card read, SSM path and scoped KMS decrypt, distinguishing execution role secret injection. Restricted files retain executable AST, description-only. Landed b073f9182dc73613005e32b4d3d694dbdd84a613, exact CI 36874121093 all four jobs successful. L-cli-a1 just check rebased candidate 1671 passed, 2 existing skips, 7977 subtests; CodeRabbit complete zero findings seven files. Root diff and exact CI readback reviewed.
<!-- SECTION:FINAL_SUMMARY:END -->
