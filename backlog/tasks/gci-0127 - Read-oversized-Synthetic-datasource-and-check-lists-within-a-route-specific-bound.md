---
id: GCI-0127
title: >-
  Read oversized Synthetic datasource and check lists within a route-specific
  bound
status: Done
assignee: []
created_date: '2026-10-07 18:24'
updated_date: '2026-10-07 19:28'
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
- [x] #1 Only the existing Synthetic datasource-discovery, check-list and probe-list GETs accept bodies up to a fixed route-specific cap of at least 32 MiB; every other guarded GET keeps MAX_GUARDED_BYTES 2 MiB, enforced by a fail-first test
- [x] #2 Concurrent reads above 2 MiB are bounded with a stated worst-case byte figure; a body over the new cap stays unavailable, never zero or absent
- [x] #3 AGENTS.md and docs/traps.md state the new route-specific cap; no new route, scope, credential or floor change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
loop16 frozen seam: fail-first route bound, bounded oversized concurrency, documented worst-case, just check, CodeRabbit and independent guarded review before push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop16: GCI-0127 (route-specific bound for oversized Synthetic reads) accepted at 73734db26d89a69b0e3d4aa19b84b5d390d738d9, implementation attempts1, review-repair rounds0. Only six owned files changed. Four exact-base fail-first native-reader source failures independently reproduced, new32MiB cap/exact-route enforcement and two process-wide survivor-held slots proven. Payload67108866bytes, conservative raw buffers134348802bytes, not RSS/general memory bound. CodeRabbit complete zero findings; CI37671405060 exact SHA and composed just check exit0 (2409passed,2skips;876s). Worker pushed without security review after reviewer infrastructure failure; root withheld acceptance/release until independent V-0127 PASS, no corrections required. Procedural violation retained, not retconned.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Three existing Synthetic GETs alone receive32MiB profile, all other guardedGETs retain2MiB. Over-cap remains transport_error/unavailable. No scope/route/credential/uid/floor changes; docs updated. Exact code, tests, external review, root security challenge, CI and composed gate accepted.
<!-- SECTION:FINAL_SUMMARY:END -->
