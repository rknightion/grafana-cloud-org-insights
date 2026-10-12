---
id: GCI-0119
title: >-
  Labelling best-practice pillar: score every stack's metrics, logs, traces and
  profiles labelling
status: Parked
assignee: []
created_date: '2026-10-06 14:43'
updated_date: '2026-10-12 21:43'
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

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop23 parent tracker-only, zero implementation attempts: conditional completion blocked on GCI-0119.15 (natural labelling dev proof). Required historical exact ECS task descriptors are now MISSING and per-task memory windows were not captured; verifier remains red. Parent AC and DoD unchecked rather than inventing every-current-stack or stability proof. Resume when the child acceptance is genuinely satisfied under its recorded artifact contract, then re-query all subtask dispositions and exact dev view evidence before parent completion.
<!-- SECTION:NOTES:END -->
