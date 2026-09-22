---
id: GCI-0029
title: Keep empty findings views publishable
status: Done
assignee:
  - '@codex'
created_date: '2026-09-22 10:35'
updated_date: '2026-09-22 11:16'
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
- [x] #1 Every shared Findings detail table declares an explicit empty-view schema.
- [x] #2 Declared schemas are checked against populated synthetic view artifacts.
- [x] #3 All dashboards publish successfully to the dev stack.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Add the missing schemas at the pillar-owned view contracts, wire them into the dashboard tables, verify against synthetic artifacts and the live dev publish, then run the repository gate and review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Dev live publish exposed two independent healthy-estate cases: empty condition-matched finding lists lacked table schemas, and an estate where every stack is explicitly unscored withheld the entire maturity view despite a satisfied dataplane input. Both now have regression coverage.

The second live dev publish showed the original risk Fleet panel still lacked the same fallback even though the shared Findings copy was fixed. Applied pillar schemas to every direct condition-matched table and added schema support to the cardinality treemap. All 11 dev dashboards then published successfully; alerts updated with existing pause and routing preserved.

Validation: just check passed with 1,489 tests, 7,290 subtests, two expected skips, both OpenTofu validations and identifier/history hygiene clean. CodeRabbit reviewed the final delta with zero findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Made every condition-matched findings table and the cardinality treemap safe on legitimate empty views, and preserved the maturity source for an explicitly all-unscored estate. Verified against synthetic artifacts, full local gates, two zero-finding CodeRabbit reviews, and a live publish of all 11 robk dashboards.
<!-- SECTION:FINAL_SUMMARY:END -->
