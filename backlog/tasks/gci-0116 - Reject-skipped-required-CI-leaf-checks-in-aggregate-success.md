---
id: GCI-0116
title: Reject skipped required CI leaf checks in aggregate success
status: Done
assignee: []
created_date: '2026-10-06 11:19'
updated_date: '2026-10-07 01:50'
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
- [x] #1 Aggregate is green only when every required leaf is explicitly successful; failed, cancelled, skipped and missing states cannot be accepted.
- [x] #2 A resource-bounded negative control observes skipped required leaves failing the aggregate, with actionlint/zizmor and independent guarded review before landing.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fail-first bounded aggregate negative control; require success for all required leaves; local validators, CodeRabbit and independent guarded review before landing.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop14: one implementation attempt, guarded review and CodeRabbit completed0 findings; fail-first actual-workflow shell negative control observed13 failures, corrected candidate rejects18 negative cases. Exact integrated SHA9fb033bdfff72765188b5427469e786005292438 just check exit0 and required GitHub CI leaves explicitly successful. Two skipped suite tests are not passes.
<!-- SECTION:NOTES:END -->
