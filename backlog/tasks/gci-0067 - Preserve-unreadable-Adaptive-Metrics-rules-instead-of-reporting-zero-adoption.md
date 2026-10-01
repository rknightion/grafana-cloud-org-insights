---
id: GCI-0067
title: Preserve unreadable Adaptive Metrics rules instead of reporting zero adoption
status: In Progress
assignee:
  - '@loop8-root'
created_date: '2026-10-01 14:18'
updated_date: '2026-10-01 21:32'
labels: []
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/pillars/cost.py
  - collector/pillars/maturity.py
priority: medium
type: bug
ordinal: 77000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop7 read-only M-seg found adaptive_metrics converts an unsuccessful rules response into an empty rule list when recommendations succeed, so rules_applied zero and adopted false can look like measured absence. This is independent of segmented savings coverage; no live failure demonstrated. Source availability and downstream cost/maturity interpretation need an honest unknown state.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A failed or malformed applied-rules read is distinguished from a successful empty list
- [ ] #2 Consumers do not present unreadable applied-rule state as measured zero or nonadoption
- [ ] #3 Offline source-to-consumer public-boundary reproduction fails before the correction and proves unknown versus measured empty
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop8 bounded implementation per frozen packet; worker owns offline reproduction/gate/review and terminal return; root owns tracker reconciliation and integrated acceptance.

L-am-a2: fix all-unknown headroom withholding and full-in-scope estate completeness guards, prove each failing first, preserve measured-population usability, rerun unchanged hydration derivation/gate, CodeRabbit and exact landed CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Root loop8 disposition S-AMR-R1 (medium materiality): CodeRabbit major finding on incomplete estate aggregates accepted. Strengthen the unlanded seam: measured per-stack values, measured-population benchmarks and explicitly labelled measured summary subtotals remain useful; unqualified estate additive rules/adoption totals are withheld/null unless every live in-scope stack has readable rule input. Unknown stacks stay excluded from unadopted lists and adoption scoring. All-unknown cost_adaptive_headroom is withheld, preserving last good view; recommendations view remains independently available. No new metric/label/catalogue or route. Existing new mixed-estate test expectations change because intended completeness contract changes, never to mask a defect. Rejected retaining unqualified partial total because it could mislead. Rejected discarding measurable per-stack inputs because source availability is independent. Reversal cost local guard/test changes before any accepted consumer; no landing yet. L-am-a1 blocked with final gate green and two unresolved majors; L-am-a2 authorized for these bounded repairs, two attempts remain afterward.
<!-- SECTION:NOTES:END -->
