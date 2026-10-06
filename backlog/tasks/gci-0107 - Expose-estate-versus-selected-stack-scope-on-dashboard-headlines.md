---
id: GCI-0107
title: Expose estate versus selected-stack scope on dashboard headlines
status: In Progress
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:46'
updated_date: '2026-10-06 15:44'
labels:
  - dashboards
  - loop13
dependencies: []
documentation:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/backlog/docs/doc-0007 -
    Loop13-dashboard-operator-relevance-review-and-dispositions.md
priority: medium
type: bug
ordinal: 123000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The operator relevance review found global collector/findings headlines next to stack-filtered tables and ranks, making selection look estate-wide or vice versa. P4 is visible wording/scope qualification only, no new selectors, formulas, metric names, data collection or series; preserve all user filters and query semantics.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Cost, Maturity, Value, Risk, Dashboard usage, Coverage and shared Findings visible headlines distinguish estate-wide versus selected-stack populations wherever those coexist, without relabelling global ratios as selected.
- [ ] #2 Assembled artifacts and selector inspection prove all/single/multiselect/prefix-collision scope is explicit with unchanged data/query contracts; just check and independent review pass.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
P4 visible population labels only across Cost/Maturity/Value/Risk/Dashboard usage/Coverage/shared Findings. Preserve selectors/formulas/data, inspect actual public artifacts and all/single/multi/prefix-collision context; truthful estate versus selected scope. Finalgate/CR as applicable and independent review before integration.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Independent proposal review found the initial named dashboard list narrower than P4 matrix. Expanded static-label scope to include Risk, Dashboard usage and Coverage; no dynamic-inventory or query change.
<!-- SECTION:NOTES:END -->
