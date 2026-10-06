---
id: GCI-0100
title: Review every dashboard and tab for operator relevance and propose improvements
status: In Progress
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-06 10:47'
labels:
  - dashboards
  - loop13
dependencies: []
priority: medium
type: task
ordinal: 116000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Read-only review of all eleven dashboards and their tabs from an org operator's view: top-N, per-stack breakdowns, trends, ranking, drill-downs, units, empty-state honesty, duplication and dead panels. Output a proposal; the root records it as a Backlog doc and tasks. Panel-only items needing zero new series and live-verified names may be admitted in loop13; anything else waits for the owner.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Proposal covers every dashboard and tab with concrete panel-level changes, each tagged panel-only or needs-series/scope/SPEC
- [x] #2 Root records it as a Backlog doc and one task per admitted change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Read-only dashboard/tab proposal; root records durable doc and admits only panel-only zero-series changes with live-name witnesses.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13: 0 implementation attempts; static proposal accepted, all eleven definitions and authored tabs mapped. Root durable doc and one task per admitted group recorded. GCI-0105 (wording honesty), GCI-0106 (publication-gap integrity), GCI-0107 (estate/selection scope) admitted after dashboard chain; remaining relevance and semantic gaps are owner tasks. No browser/live proof claimed.
<!-- SECTION:NOTES:END -->
