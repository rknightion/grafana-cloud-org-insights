---
id: GCI-0035
title: Publish bounded datasource-type detail for Grafana query surfaces
status: Parked
assignee: []
created_date: '2026-09-23 18:35'
updated_date: '2026-09-23 19:52'
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
<!-- SECTION:NOTES:END -->
