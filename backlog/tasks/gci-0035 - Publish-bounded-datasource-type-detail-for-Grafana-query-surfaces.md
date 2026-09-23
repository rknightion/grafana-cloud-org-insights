---
id: GCI-0035
title: Publish bounded datasource-type detail for Grafana query surfaces
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
ordinal: 45000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 2 - high value, moderate cost. Live usage-insights lines carry datasourceType and panelPluginId but generic scenes merges multiple apps. Add a bounded per-stack view of datasource-type and panel-type query mix through the existing exact instance_id guard, without claiming per-app attribution. Proposed new emitted series: 0; point-in-time detail is a view.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Top-N view is bounded and scoped to exact instance_id on every query
- [ ] #2 Dashboard explains that datasource type is inference, not app identity
- [ ] #3 Raw datasource or plugin values never become metric labels
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

Wave 2 code landed at a070885: bounded top-20 plus remainder query mix per live stack, scoped by exact instance_id, no new metrics. Four implementation attempts; final CodeRabbit had one valid non-finite input finding, reproduced and fixed by root. Focused 154 passed, 794 subtests. Guarded dev read found 368 and 183 requests on active stacks with datasourceType, but no non-empty panelPluginId; panel positive proof remains unavailable. Final exact-SHA gate, CI and dev readback pending.
<!-- SECTION:NOTES:END -->
