---
id: GCI-0119
title: >-
  Labelling best-practice pillar: score every stack's metrics, logs, traces and
  profiles labelling
status: To Do
assignee: []
created_date: '2026-10-06 14:43'
labels:
  - labelling
dependencies: []
documentation:
  - backlog/docs/doc-0008 - Labelling-best-practice-research-and-rulebook.md
priority: high
type: enhancement
ordinal: 135000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Estate-wide, deterministic assessment of each live stack's labelling and OTel attribute practice against Grafana, OpenTelemetry and Professional Services guidance, published as views, a bounded score and a labelling dashboard for platform operators. Owner decisions D-LBL1 to D-LBL11 (2026-10-06), the merged rulebook, the frozen evaluator contracts, the metric plan and the dependency order are in doc-0008 Part 1. Order: subtask A first; then B and C1-C4; D after B; I after D; each E after its C and D, serially; F after B and D; G after F; K after D, F, G and I; H, L and M after K; J parked. No customer name may appear in this repository.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 All subtasks Done, or Parked with a recorded reason
- [ ] #2 The labelling dashboard shows every live stack with score, coverage and catalogue_version on the dev deployment
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
