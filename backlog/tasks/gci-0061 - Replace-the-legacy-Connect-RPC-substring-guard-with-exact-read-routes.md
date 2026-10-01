---
id: GCI-0061
title: Replace the legacy Connect-RPC substring guard with exact read routes
status: In Progress
assignee:
  - '@loop7-root'
created_date: '2026-10-01 11:45'
updated_date: '2026-10-01 13:51'
labels:
  - security
  - transport
dependencies: []
references:
  - collector/sources/dataplane.py
  - collector/sources/label_risk.py
priority: medium
type: chore
ordinal: 71000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 documentation audit at fb5803a found collector/sources/dataplane.py:70 permits POST based on Service/List or QuerierService substring matching. The only current callers are the exact Fleet ListCollectors and ListPipelines routes at lines343-344; the broader guard is not needed for them and is distinct from the ratified two-path label-risk exception. This is preventive boundary hardening, not evidence of a live mutating call. No new route or POST authority is granted.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The helper admits only explicitly authorized exact read routes, with no substring or query-string bypass
- [ ] #2 Current Fleet list reads still work while unapproved methods and paths are refused
- [ ] #3 The general HTTP client remains GET-only and the dedicated label-risk POST exception remains separately bounded
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop7 frozen packets: bounded implementation or AC1 research; public-boundary proof, offline gate and CodeRabbit before landing, exact landed CI. Root security review/guard landing, research staff GET probe and conditional reserve decision, integrated review, stable release and dev-only rollout proof. Tracker remains root-owned.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Owner correction Rob 2026-10-01: three current helper routes, not two: CollectorService/ListCollectors, PipelineService/ListPipelines, QuerierService/LabelValues (signal_inventory.py). Exact frozen S-RPC guard; GET-only general client and label-risk two-path exception unchanged. Published AGENTS wording is tracked separately, never hand-edited.
<!-- SECTION:NOTES:END -->
