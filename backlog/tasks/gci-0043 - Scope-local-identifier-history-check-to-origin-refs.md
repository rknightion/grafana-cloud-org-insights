---
id: GCI-0043
title: Scope local identifier history check to origin refs
status: Done
assignee:
  - '@loop3-root'
created_date: '2026-09-23 22:22'
updated_date: '2026-09-30 12:29'
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
- [x] #1 A history-check mode scans only refs reachable from origin without changing the shipped-text pattern or rewriting history
- [x] #2 Local gate and hosted CI classify the same origin commit set while retained local-only refs remain untouched
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop3 P-0043: reproduce local-only versus origin-reachable identifier refs, implement origin-scoped history mode without changing patterns or refs, run final just check/CodeRabbit and exact-SHA CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
loop3 P-0043-a1 delivered origin-ref local history mode and actual local/CI recipe regressions without changing patterns, retained tags or history. Root reviewed exact diff. Landed SHA 2e901eb0106de1c9c775487611e9c3ca891fcdfb; full just check green (1571 passed, 2 existing skipped), CodeRabbit completed zero findings/all 3 files reviewed; exact-SHA CI 36714635455 success. Evidence codex/loop3-evidence/P-0043. No infrastructure retries; a2 unused.
<!-- SECTION:FINAL_SUMMARY:END -->
