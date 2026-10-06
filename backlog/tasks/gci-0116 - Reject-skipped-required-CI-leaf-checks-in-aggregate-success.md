---
id: GCI-0116
title: Reject skipped required CI leaf checks in aggregate success
status: To Do
assignee: []
created_date: '2026-10-06 11:19'
labels:
  - ci
  - owner-decision
dependencies: []
priority: medium
type: bug
ordinal: 132000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The guarded loop13 release review found that the existing CI aggregate rejects failed or cancelled required jobs but can treat skipped required leaves as success. This loop directly checked all required leaves at each accepted SHA. A later gate repair needs guarded workflow scope and does not follow from a green aggregate.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Aggregate is green only when every required leaf is explicitly successful; failed, cancelled, skipped and missing states cannot be accepted.
- [ ] #2 A resource-bounded negative control observes skipped required leaves failing the aggregate, with actionlint/zizmor and independent guarded review before landing.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
