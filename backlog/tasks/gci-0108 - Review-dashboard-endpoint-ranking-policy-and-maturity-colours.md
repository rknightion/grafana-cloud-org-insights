---
id: GCI-0108
title: Review dashboard endpoint-ranking policy and maturity colours
status: Done
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 17:39'
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
ordinal: 124000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
P3: range top-N unions can resurrect historical members, and maturity threshold colouring appears inverted. Retain useful historical trends; owner prioritisation and rendered moving-membership proof are needed before broad changes.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A rendered changing-membership fixture distinguishes current endpoint queues from historical unions, sorts worst first and uses honest maturity colours without new series.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Bounded rendered changing-membership fixture separates endpoint current-queue/ranking semantics from historical unions/trends, retains truthful history, worst-first display and honest absolute maturity colours/missing-score state. No source/schema/new series. Preserve accepted raw-unit/metadata/attribution and frozen tabs. Public-boundary fixture first red then green, final gate, exactbase CodeRabbit/independent review and root-only land.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: implementation cycles2 (candidate gate, then valid minor absence-copy correction/finalgate), review-repair rounds0. Exact4file patchb577de887 accepted after changing-membership baseline fail-first/final witness through real local Prometheus3.15 and Grafana12.2 registered transformations/getDisplayProcessor. Endpoint queues bounded/current-at-selected-endpoint, historical union/trends retained labelled; existing absolute25/50/75rubric colours and null/NaN Not scoredgray truthful, measured0red distinct. No freshcurrentestate/browserpaint/deployed claim. Exactbase CodeRabbit completeall4major0/unreviewed0, minorwordingfixed trivialdelta; independentPASS. Root source5fddabdf7224219ba348d64248bf9be384b45baf landed; composedsameSHA just check0 (2687pass,2 existing skipsnotpasses,37Tofu), exactrequiredCI38284439434 allleavessuccess. No source/schema/newseries/roster. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/rank-colours/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Rendered engine-level changing-membership and absolute-colour contract exercised and corrected without new series. Useful historical candidates remain explicitly historical; unavailable scores are not zero/good. Exact integrated local and required CI proof passed.
<!-- SECTION:FINAL_SUMMARY:END -->
