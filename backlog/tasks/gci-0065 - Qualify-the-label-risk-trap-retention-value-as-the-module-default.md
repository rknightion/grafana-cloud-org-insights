---
id: GCI-0065
title: Qualify the label-risk trap retention value as the module default
status: In Progress
assignee:
  - '@loop7-root'
created_date: '2026-10-01 12:01'
updated_date: '2026-10-01 13:51'
labels:
  - documentation
  - privacy
dependencies: []
references:
  - docs/traps.md
  - docs/configuration.md
  - terraform/storage.tf
priority: low
type: docs
ordinal: 75000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop6 independent cross-document review at4f0b5fa found docs/traps.md:712-714 states private scans retain an existing90-day lifecycle, while current configuration and storage code use positive configurable scan_retention_days for scans and the raw-match view. Ninety is the module default, not a fixed retention promise. This file was excluded from all loop6 edit ownership, so the note is explicitly tracked instead of silently changing its contract.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The trap states90days is a module default and links to the canonical configurable current/noncurrent retention contract
- [ ] #2 No fixed observation-age erasure promise or broader view-expiry claim is introduced
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
