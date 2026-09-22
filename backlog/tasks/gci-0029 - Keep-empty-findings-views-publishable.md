---
id: GCI-0029
title: Keep empty findings views publishable
status: In Progress
assignee:
  - '@codex'
created_date: '2026-09-22 10:35'
updated_date: '2026-09-22 10:39'
labels: []
dependencies: []
modified_files:
  - bin/dashboards.py
  - collector/pillars/cost.py
  - collector/pillars/maturity.py
  - collector/pillars/risk.py
  - tests/test_dashboards.py
  - tests/test_maturity.py
priority: high
type: bug
ordinal: 38000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Dashboard publication must succeed when a condition-matched findings view is legitimately empty. The live dev estate exposed missing explicit schemas in shared Findings tables.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every shared Findings detail table declares an explicit empty-view schema.
- [ ] #2 Declared schemas are checked against populated synthetic view artifacts.
- [ ] #3 All dashboards publish successfully to the dev stack.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add the missing schemas at the pillar-owned view contracts, wire them into the dashboard tables, verify against synthetic artifacts and the live dev publish, then run the repository gate and review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dev live publish exposed two independent healthy-estate cases: empty condition-matched finding lists lacked table schemas, and an estate where every stack is explicitly unscored withheld the entire maturity view despite a satisfied dataplane input. Both now have regression coverage.
<!-- SECTION:NOTES:END -->
