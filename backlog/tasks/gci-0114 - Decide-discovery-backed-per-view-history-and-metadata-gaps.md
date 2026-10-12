---
id: GCI-0114
title: Decide discovery-backed per-view history and metadata gaps
status: To Do
assignee: []
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 11:49'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
D-DOC23 bounded display contract proposed by loop23 root: failed inventory means current membership unknown, never zero or a historical label union called fresh discovery; retain last-good view and expose its own timestamp. A removed-stack row is excluded only when existing reliable current inventory proves departure, otherwise label membership historical/unknown, never manufacture a configured roster. Missing per-view metadata yields unknown age/completeness, not inferred current from run time. Last-good publication time and input-observation time are distinct, with advancing staleness from existing supported metadata; measured-empty requires an available measured input, absent input is unavailable. Schema/source needed to prove membership or completeness becomes a named follow-up packet, not part of this dashboard-only build.
<!-- SECTION:NOTES:END -->
