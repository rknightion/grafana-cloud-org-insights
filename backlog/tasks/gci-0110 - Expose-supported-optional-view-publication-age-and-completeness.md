---
id: GCI-0110
title: Expose supported optional-view publication age and completeness
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
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
P6: hourly composition does not make daily product observations fresh. Existing metadata must be inspected before distinguishing unavailable, disabled, measured-empty and last-good states; absent metadata is not permission to change schema.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Rendered absent, measured-empty, old last-good, partial and permission-error cases are honest; supported publication/input timestamps remain distinct, with new schema needs separately approved.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
