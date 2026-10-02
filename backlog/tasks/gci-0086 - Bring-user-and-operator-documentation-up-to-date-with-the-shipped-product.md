---
id: GCI-0086
title: Bring user and operator documentation up to date with the shipped product
status: To Do
assignee: []
created_date: '2026-10-02 13:50'
updated_date: '2026-10-02 13:50'
labels:
  - docs
dependencies:
  - GCI-0085
priority: low
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Many pillars, views, reader tokens and dashboards have landed since the docs were last reviewed as a whole. Once the main feature backlog is cleared, review README, SPEC.md, CAPABILITIES.md, RUNBOOK.md, docs/ and terraform/README.md against the current code and dashboards. Run after the dashboard inventory task so the docs describe the remediated panels.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every dashboard, view, opt-in reader token and configuration variable that ships is described in the docs, checked against the code and assembled dashboards rather than memory
- [ ] #2 Statements that no longer hold (removed features, changed scopes, superseded runbook steps) are corrected or removed; BUDGET.md stays generator-only
- [ ] #3 Docs build and existing doc lint pass; no customer identifier appears
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
