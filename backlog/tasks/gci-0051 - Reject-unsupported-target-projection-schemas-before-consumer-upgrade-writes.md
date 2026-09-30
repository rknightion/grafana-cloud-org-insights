---
id: GCI-0051
title: Reject unsupported target projection schemas before consumer upgrade writes
status: In Progress
assignee:
  - '@loop3-root'
created_date: '2026-09-30 14:40'
updated_date: '2026-09-30 14:42'
labels:
  - consumer
  - rollback
dependencies: []
references:
  - bin/consumer_manifest.py
  - consumer/MIGRATION-RUNBOOK.md
priority: medium
type: bug
ordinal: 61000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Independent loop3 review reproduced new consumer_manifest upgrade reporting success for a v0.3.0 target while retaining the new scanner policy key and digest. Actual old tooling rejects that manifest. Saved-triplet restoration is safe, but the successful shortcut is misleading and can break a downgrade. Scope is a fail-closed target-schema guard, not general cross-version migration.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An incompatible target projection schema is rejected before changing manifest or Terraform files, with a clear instruction to use target-matched tooling or the saved rollback triplet
- [ ] #2 Supported forward legacy migration still verifies old digests, preserves provisioner policy and passes actual CLI contracts
- [ ] #3 The documented saved-triplet rollback remains valid and is not replaced by blind regeneration
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fail closed before writes when the verified requested target projection schema differs from this tool; preserve supported forward migration and current strict checks. Reproduce through the real upgrade CLI and assert files remain unchanged. Do not implement general downgrade conversion or execute untrusted target code; saved old-triplet restoration remains the run rollback strategy.
<!-- SECTION:PLAN:END -->
