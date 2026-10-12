---
id: GCI-0108
title: Review dashboard endpoint-ranking policy and maturity colours
status: In Progress
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 16:52'
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
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
P3: range top-N unions can resurrect historical members, and maturity threshold colouring appears inverted. Retain useful historical trends; owner prioritisation and rendered moving-membership proof are needed before broad changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A rendered changing-membership fixture distinguishes current endpoint queues from historical unions, sorts worst first and uses honest maturity colours without new series.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Bounded rendered changing-membership fixture separates endpoint current-queue/ranking semantics from historical unions/trends, retains truthful history, worst-first display and honest absolute maturity colours/missing-score state. No source/schema/new series. Preserve accepted raw-unit/metadata/attribution and frozen tabs. Public-boundary fixture first red then green, final gate, exactbase CodeRabbit/independent review and root-only land.
<!-- SECTION:PLAN:END -->
