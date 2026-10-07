---
id: GCI-0127
title: >-
  Read oversized Synthetic datasource and check lists within a route-specific
  bound
status: To Do
assignee: []
created_date: '2026-10-07 18:24'
updated_date: '2026-10-07 18:24'
labels:
  - synthetic
  - deployment-blocker
dependencies: []
priority: high
ordinal: 162000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
GCI-0125 owner disposition (Rob, 2026-10-07): fix forward. Loop15 customer T2 lost three stacks to the 2 MiB guarded-body cap on the existing Synthetic GETs (datasource discovery bodies of 6.3 MB and 11.0 MB, one check list over 2 MiB). Raise the cap only for the three existing Synthetic GETs, keep 2 MiB everywhere else, add no route, and bound the concurrent oversized reads. Evidence: /Users/rob/repos/grafana-cloud-org-insights/codex/loop15-evidence/R-cust/synthetic-failure-traces.json
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Only the existing Synthetic datasource-discovery, check-list and probe-list GETs accept bodies up to a fixed route-specific cap of at least 32 MiB; every other guarded GET keeps MAX_GUARDED_BYTES 2 MiB, enforced by a fail-first test
- [ ] #2 Concurrent reads above 2 MiB are bounded with a stated worst-case byte figure; a body over the new cap stays unavailable, never zero or absent
- [ ] #3 AGENTS.md and docs/traps.md state the new route-specific cap; no new route, scope, credential or floor change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
