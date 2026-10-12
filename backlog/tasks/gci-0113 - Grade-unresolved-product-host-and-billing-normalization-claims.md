---
id: GCI-0113
title: Grade unresolved product host and billing normalization claims
status: In Progress
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 15:19'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23 progress: four implementation attempts used (two worker change/verify cycles, first and final rescue); review-repair rounds2. Actual currency formatters and15 affected raw-derived panel labels neutralized; remaining header/help/row/diagnostic context corrected with canonical tabs and query math preserved. Final artifact759526b28886eeaa1b0bee8f33a1dffe535b907e1ecca28e56ed7f516d7a0d6e passed real fail-first/public CLI/known GBP pricing controls and full just check0. Same independent reviewer clarified its last generic Money/billed-line concern as nonblocking ambiguity, not a figure/currency/period claim; no code fifth attempt. Exact final delta CodeRabbit pending against content-identical prior snapshot1e551481. Not landed/Done yet. Full evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/raw-units/rescue/final/.
<!-- SECTION:NOTES:END -->
