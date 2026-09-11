---
id: GCI-0006
title: Prove hosted CI at an exact source revision
status: Done
assignee: []
created_date: '2026-08-24 12:02'
updated_date: '2026-09-11 14:01'
labels: []
dependencies: []
references:
  - backlog/docs/doc-0005 - Genericisation-history-and-validation-evidence.md
priority: low
type: task
ordinal: 6000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Capture a successful hosted CI run for an immutable product revision. The current account-wide GitHub Actions billing failure is an external availability condition, not a code failure; do not change billing or weaken gates to complete this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A hosted run records the exact commit and executes the repository customer-identifier, test, and Terraform gates
- [x] #2 Any billing-related inability to start is reported as unavailable evidence rather than a failed product gate
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Satisfied by hosted CI run 34606034103 at exact source revision 7a7585ed756709b8dade8eff0c878f3cabe26555 (event: push, conclusion: success). Jobs pytest, tofu validate, no leaked identifiers and the ci-success aggregator all completed successfully, so AC1's three gates are all recorded against the immutable revision. AC2 is moot rather than unmet: the account-wide Actions billing failure that parked this task is no longer in effect, so no unavailable-evidence report was needed. Verified 2026-09-11 during wave 1 closeout.
<!-- SECTION:NOTES:END -->
