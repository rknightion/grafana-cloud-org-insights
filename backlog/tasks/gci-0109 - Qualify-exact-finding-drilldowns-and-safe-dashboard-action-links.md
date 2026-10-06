---
id: GCI-0109
title: Qualify exact finding drilldowns and safe dashboard action links
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
ordinal: 125000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
P5: finding detail conditions can differ from their headline counts, and numeric-only registers lack reliable navigation. Link identity schemas and privacy need independent verification; no inferred hostnames or sensitive URL values.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each admitted link resolves only from existing permitted identity fields and carries intended selection/time; detail populations match finding predicates. Missing identity never invents a destination.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
