---
id: GCI-0043
title: Scope local identifier history check to origin refs
status: In Progress
assignee:
  - '@loop3-root'
created_date: '2026-09-23 22:22'
updated_date: '2026-09-30 12:26'
labels: []
dependencies: []
priority: high
ordinal: 53000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The local history checker scans every local Git ref. Eight pre-scrub commits remain reachable through a local-only RC tag and make local history mode red, while hosted CI checks origin refs and passes. The tag is retained for now and must not be pushed or deleted as part of this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A history-check mode scans only refs reachable from origin without changing the shipped-text pattern or rewriting history
- [ ] #2 Local gate and hosted CI classify the same origin commit set while retained local-only refs remain untouched
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop3 P-0043: reproduce local-only versus origin-reachable identifier refs, implement origin-scoped history mode without changing patterns or refs, run final just check/CodeRabbit and exact-SHA CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.
<!-- SECTION:NOTES:END -->
