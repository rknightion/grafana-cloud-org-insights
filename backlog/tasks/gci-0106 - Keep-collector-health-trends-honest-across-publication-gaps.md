---
id: GCI-0106
title: Keep collector health trends honest across publication gaps
status: Done
assignee:
  - '@loop13-root'
created_date: '2026-10-06 10:46'
updated_date: '2026-10-06 15:44'
labels:
  - dashboards
  - loop13
dependencies: []
documentation:
  - >-
    /Users/rob/repos/grafana-cloud-org-insights/backlog/docs/doc-0007 -
    Loop13-dashboard-operator-relevance-review-and-dispositions.md
priority: high
type: bug
ordinal: 122000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The operator relevance review found Estate failure bars with unconditional zero fallback and integrity trends that bridge missing observations. P2 uses only existing collector metrics and existing success/staleness policy. No new vendor metric, collector series, reader or schema is permitted. If existing completion policy cannot qualify zero at the correct tier/window, stop rather than invent one.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A stopped or stale publisher is unavailable/gapped rather than healthy zero; healthy complete scans with no failures may render zero only when qualified by existing matching completion evidence.
- [x] #2 Freshness, availability and failure integrity trends do not interpolate across gaps; any intentionally retained bridging outside integrity trends is documented. Real assembled artifact and synthetic state proof, just check, CodeRabbit and independent review pass.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
P2 integrity-only: inspect existing completion/freshness policy and real artifact expressions; red-first stopped/stale/healthy-zero public query reproduction. No arbitrary cutoff or new metric/schema. Remove false-health fallbacks/bridging only where matching completion evidence suffices, otherwise stop and return precise contract gap. Final gate/CR and independent review before integration.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop13:2change/verify cycles,1review-repair round. Endpoint-only matching-tier completecoverage/owncompletion failures with existing alert3h/36h/18h policy and24h observationwindow; fiveintegrity trends points-only/gapped. Chronologicalbaseline artifact andrealengine red,59finalextracted-expressioncasesgreen, onlysixEstatepanels changed with other11artifactcontracts unchanged. CRmajor sparseomitted-timestamp interpolation fixed; complete0findingdelta after reviewedcheckpoint. Independent immutable/publication/carry conformancePASS. Landed6c0876295dfeedec18a4453329d7b4b9b837a037 final+composed justcheck2206passed2skipped13429subtests and exactCI37488924919 required leaves success. No immediateprocessliveness/eventcounts/all-tier-health/browserclaim.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Removed manufactured historical healthy zeros and bridging across publication gaps using existing per-tier completion policy, explicit completecoverage, endpoint-only results and points-only integrity observations.
<!-- SECTION:FINAL_SUMMARY:END -->
