---
id: GCI-0113
title: Grade unresolved product host and billing normalization claims
status: In Progress
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 13:44'
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
ordinal: 129000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
N2: later usage-matrix corrections leave host-hour, service overlap and money/period contracts unresolved. Metric spelling and roster occurrence do not prove billable units. Existing showback tasks own their bounded accepted work; this captures remaining interpretation gaps.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner grades raw qualified observations versus withholding; every additional normalization/conversion has authoritative unit, period, overlap and population evidence, and unknown dimensions remain unknown.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-DOC23 dashboard-only build: audit unresolved product host/billing units and periods, label retained observations raw, not normalised with unknown units/overlap/population preserved. No added conversions or new sources/series. Preserve accepted existing independently proven normalized models. Real assembled artifact regression, just check, independent review and CodeRabbit before root-only land.
<!-- SECTION:PLAN:END -->
