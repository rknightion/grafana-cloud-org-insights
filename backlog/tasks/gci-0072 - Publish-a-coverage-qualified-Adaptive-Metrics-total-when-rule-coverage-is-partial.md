---
id: GCI-0072
title: >-
  Publish a coverage-qualified Adaptive Metrics total when rule coverage is
  partial
status: To Do
assignee: []
created_date: '2026-10-02 08:17'
labels:
  - adaptive-metrics
  - accuracy
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/pillars/cost.py
priority: medium
type: enhancement
ordinal: 82000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop8 S-AMR withholds unqualified estate Adaptive Metrics totals (applied rules, savings, headroom) whenever any live in-scope stack's rules read fails. On a large estate one transient failure hides the headline figure and leaves an older last-good copy. Owner decision (Rob, 2026-10-02): when coverage is partial, publish the measured total explicitly qualified as covering N of M live in-scope stacks, never labelled or summed as the estate total; a fully measured estate keeps the unqualified total. Gaps stay absent, never zero.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 When rule coverage is partial, the cost/adaptive views publish the measured total with measured and live in-scope stack counts, and nothing presents it as the estate total
- [ ] #2 Full coverage still publishes the unqualified estate total; zero coverage publishes no total; findings gauges keep the loop8 complete-coverage rule unless the owner-approved qualified form is explicitly declared
- [ ] #3 Any new metric is declared in budget.py CATALOGUE with a time-series justification, BUDGET.md is regenerated, VIEW_INPUTS re-derives cleanly, and a public-boundary proof crosses compose into the dashboards/findings consumers
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
