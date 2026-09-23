---
id: GCI-0040
title: Find a defensible per-app discriminator for Scenes query events
status: To Do
assignee: []
created_date: '2026-09-23 18:35'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: low
type: enhancement
ordinal: 50000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 7 - valuable but upstream-dependent. In a live 55-stack sample, scenes lines contained datasource and dashboard fields but no plugin or URL field. Determine whether an upstream enrichDataRequest change or a different existing source can distinguish Metrics, Logs, Traces and Profiles Drilldown and other Scenes apps. Proposed new emitted series: 0 until a discriminator is proven; any future enum metric would cost live stacks times the approved bounded enum.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A known app query is observed before and after any proposed discriminator
- [ ] #2 A single source value is never attributed to a specific app by datasource type alone
- [ ] #3 The result is documented as supported or unavailable with the exact evidence
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
