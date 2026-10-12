---
id: GCI-0112
title: Decide the OnCall matched-window engagement contract
status: In Progress
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 11:40'
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
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
N1: gauge group populations and seven-day histogram observations do not establish a matched acknowledgement-share denominator. Existing ratios may imply an unsupported cohort or causal outcome. No new live research or semantic change is granted by this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner decides separately qualified counts versus matched-cohort research; any retained quantitative ratio has independent population/window evidence, otherwise it is withheld without calling unknown zero.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-DOC23 build: retain separately qualified OnCall group counts and 7d response bands, withhold unmatched acknowledgement ratios with reason. Implement rendered dashboard contract, gate just check, independent review and root-only land.
<!-- SECTION:PLAN:END -->
