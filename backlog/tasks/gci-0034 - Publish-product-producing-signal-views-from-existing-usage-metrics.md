---
id: GCI-0034
title: Publish product producing-signal views from existing usage metrics
status: Parked
assignee: []
created_date: '2026-09-23 18:35'
updated_date: '2026-09-23 23:47'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: high
type: enhancement
ordinal: 44000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 1 - high value, low implementation cost. The two live write-stack usage datasources expose 325 metric names, but a positive rate, an active gauge and a billing-period quantity mean different things. Build bounded per-stack views for product producing signals from the existing write-stack reader, with explicit windows and absent-not-zero behavior. Proposed new emitted series: 0; point-in-time views and direct panels suffice.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Each product signal has a documented metric-specific window, unit and nonzero interpretation
- [ ] #2 Views distinguish missing input from measured zero and never infer human UI use
- [ ] #3 No raw metric names or stack identifiers become new metric labels
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked at Wave 1 boundary: researched build candidate in doc-0006, outside this wave implementation scope. Resume when Rob selects the next product work; first verify the candidate metric or datasource contract named in this task.

Wave 2 code landed at 6ecd68b: coverage_producing_signals is a point-in-time view of documented Metrics active series and Traces bytes per second, each using the capability-adoption 24-hour peak. Missing, measured zero and positive are distinct; no human UI use is inferred. No metrics or labels were added. CodeRabbit completed with zero findings; targeted checks 217 passed, 2 skipped. Final exact-SHA gate, CI and dev readback pending.
<!-- SECTION:NOTES:END -->
