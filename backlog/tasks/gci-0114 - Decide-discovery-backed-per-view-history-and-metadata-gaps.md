---
id: GCI-0114
title: Decide discovery-backed per-view history and metadata gaps
status: To Do
assignee: []
created_date: '2026-10-06 10:47'
labels:
  - dashboards
  - owner-decision
dependencies: []
documentation:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/backlog/docs/doc-0007 -
    Loop13-dashboard-operator-relevance-review-and-dispositions.md
priority: medium
type: task
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
N3: exact current-estate membership and per-view completeness may need schema or source changes beyond panel-only work. Historical label membership is not fresh discovery. No series or schema work is admitted here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner approves bounded input/schema scope before implementation; proposed contract proves failed inventory, removed stack, missing metadata and last-good cases without configured estate rosters.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
