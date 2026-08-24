---
id: GCI-0006
title: Prove hosted CI at an exact source revision
status: Parked
assignee: []
created_date: '2026-08-24 12:02'
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
- [ ] #1 A hosted run records the exact commit and executes the repository customer-identifier, test, and Terraform gates
- [ ] #2 Any billing-related inability to start is reported as unavailable evidence rather than a failed product gate
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
