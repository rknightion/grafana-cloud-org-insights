---
id: GCI-0066
title: >-
  Correct published AGENTS Pyroscope read-POST wording to distinguish the exact
  three-route helper
status: Done
assignee:
  - '@loop8-root'
created_date: '2026-10-01 13:51'
updated_date: '2026-10-01 21:37'
labels: []
dependencies: []
references:
  - AGENTS.md
  - collector/sources/dataplane.py
  - collector/sources/signal_inventory.py
priority: medium
type: docs
ordinal: 76000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
AGENTS.md is maintained directly in this repository. Loop7 found its label-risk-alone wording contradicted the approved exact three-route Connect-RPC helper. D-0066 authorizes a root edit distinguishing the helper from the separate native label-risk two-route exception, without new routes or authority.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Repository AGENTS.md distinguishes the exact three CONNECT_RPC_READ_ROUTES helper routes from the dedicated label-risk two-route native read-POST exception
- [x] #2 Root-edited AGENTS.md agrees with implemented HTTPS/no-redirect boundaries without widening route or live-write authority; just check and exact landed CI pass
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root edit exact boundaries; validate against source; run just check; land under the lane-push mutex; observe exact CI; include integrated review.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop8 D-0066 corrects the external canonical publisher premise: AGENTS.md is maintained here; the external publisher writes only backlog/docs/doc-0001.

Loop8 root corrected repository AGENTS.md directly under D-0066: exact three Connect-RPC helper parsed-path suffixes over HTTPS/no redirects versus separate label-risk native two-route exception. General HTTP client stays GET-only; no new route/live-write authority. Landed afafa2271480094abfe314671fcb405e73d30762; final local just check passed before push; exact CI 36929717903 success with all four jobs, one watcher and one terminal readback. CodeRabbit skipped documentation-only clarification, independent R-int will review boundaries against implemented source.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Corrected external-publisher premise and boundary wording without broadening authority. Exact landed CI 36929717903 and offline gate green; evidence codex/loop8-evidence/R-agents.
<!-- SECTION:FINAL_SUMMARY:END -->
