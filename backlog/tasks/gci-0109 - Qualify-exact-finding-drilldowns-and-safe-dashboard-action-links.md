---
id: GCI-0109
title: Qualify exact finding drilldowns and safe dashboard action links
status: Parked
assignee: []
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 21:43'
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

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement only frozen D-LINK23 section3 links1-10 after the ownership prerequisite; explicit missing-slug no-link and unmatched stack_id row-retention/no-link before conditional7, All/single/multi plus gcinsight/consumer prefix and time proof, final assembled target IDs, predicates exactly SPECS. Never hostname inference, email/uid/label/service/cluster/raw evidence in URLs; no new source/schema/identity.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop23 zero implementation attempts: dependency park. Frozen prerequisite GCI-0122 (per-tab field and enum ownership) reached its ceiling without acceptance, so no safe serial source/ownership contract was released. Resume after that task is accepted; no links implemented by bypassing dependency. Existing section1 static canonical links are already accepted, but do not fulfill all section3 actions.
<!-- SECTION:NOTES:END -->
