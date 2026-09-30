---
id: GCI-0051
title: Reject unsupported target projection schemas before consumer upgrade writes
status: Done
assignee:
  - '@loop3-root'
created_date: '2026-09-30 14:40'
updated_date: '2026-09-30 15:21'
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
- [x] #1 An incompatible target projection schema is rejected before changing manifest or Terraform files, with a clear instruction to use target-matched tooling or the saved rollback triplet
- [x] #2 Supported forward legacy migration still verifies old digests, preserves provisioner policy and passes actual CLI contracts
- [x] #3 The documented saved-triplet rollback remains valid and is not replaced by blind regeneration
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fail closed before writes when the verified requested target projection schema differs from this tool; preserve supported forward migration and current strict checks. Reproduce through the real upgrade CLI and assert files remain unchanged. Do not implement general downgrade conversion or execute untrusted target code; saved old-triplet restoration remains the run rollback strategy.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
loop3 target-schema guard completed at0711fbca590be253e3ad20316e1e0968e16d963c, CI36734938281success. Static exact Git-artifact literal schema comparison rejects incompatible/unsupported targets before journal recovery or manifest/tf writes; no target code executed. Real CLI proves unchanged files and supported legacy forward validation/carry. Saved-triplet rollback remains with old target tooling. GCI0051a1 CI36733739525 failed shallow-history fixture; a2 preserved captured actual old declarations in temporary real Git objects, final gate1647passed2existing skipped7966subtests. CodeRabbit major unsupported augmented writes fixed, final reviews0findings/allchangedpaths; infra0, bothattemptsused. Root reviewed actual application/docs diff; no source/permission/infra drift.
<!-- SECTION:FINAL_SUMMARY:END -->
