---
id: GCI-0114
title: Decide discovery-backed per-view history and metadata gaps
status: Done
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 16:19'
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
ordinal: 130000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
N3: exact current-estate membership and per-view completeness may need schema or source changes beyond panel-only work. Historical label membership is not fresh discovery. No series or schema work is admitted here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner approves bounded input/schema scope before implementation; proposed contract proves failed inventory, removed stack, missing metadata and last-good cases without configured estate rosters.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-DOC23 schema-free build from existing supported view metadata only. Apply recorded bounded display contract to failed inventory/current-membership uncertainty, removed-stack/unknown departure, missing metadata and last-good publication/input age. Prove changing-state fixtures through actual built artifacts; no new source/schema/series/configured roster. Root records any necessary source/schema gap as a named implementable follow-up, not code here. One final gate, independent review, exact-base CodeRabbit and root land.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
D-DOC23 bounded display contract proposed by loop23 root: failed inventory means current membership unknown, never zero or a historical label union called fresh discovery; retain last-good view and expose its own timestamp. A removed-stack row is excluded only when existing reliable current inventory proves departure, otherwise label membership historical/unknown, never manufacture a configured roster. Missing per-view metadata yields unknown age/completeness, not inferred current from run time. Last-good publication time and input-observation time are distinct, with advancing staleness from existing supported metadata; measured-empty requires an available measured input, absent input is unavailable. Schema/source needed to prove membership or completeness becomes a named follow-up packet, not part of this dashboard-only build.

D-DOC23 source/schema gap recorded as GCI-0134 (approve current-estate and exact view-provenance evidence), parked for owner scope/compatibility approval. Existing snapshots and historical label_values cannot prove current identity/departure; generated_at is an envelope marker, not exact S3 upload or source observation, and generic completeness is unknown. Schema-free candidate uses runtime queries to exact existing view URLs, no roster or source field added. Actual four-state CLI artifacts and408JSONata selectors evaluated2.2.2, knownavailable ages advance while missing/unavailable ages stay unknown; independent review found no correctness blocker. No browser/deployed-plugin proof. Exactbase CodeRabbit complete0/all6files and final just check0; candidate not yet integrated.

loop23 completed: implementation attempts1, review-repair rounds0; preparatory fail-first fixture/syntax errors corrected before production candidate, no infrastructure/test weakening. Exact6file patchdcbd4b3 accepted after real four-state CLI artifacts/408JSONata selectors, preserved source-lineage coverage, CodeRabbit complete0/all6files and independent reviewer PASS. Sourceb39542087618ae83078f82cc2d0ca2ffb2acdcd4 landed; composed sameSHA just check0 (2678pass,2 existing unidentified skips not passes,37Tofu), exact required CI38274888339 all leaves success. Runtime companions show retained envelope marker and estimated available-input provenance age, no exactS3 upload/source-time/current-roster/completeness claim. Historical rows preserved, missing metadata unknown, no source/schema/series/reader change; owner packet GCI-0134 (approve current-estate and exact view-provenance evidence) is recorded separately. Proof is local expression/public-artifact, not browser/deployed-plugin. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/view-metadata/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
D-DOC23 bounded history/metadata display shipped on main: conservative runtime metadata companions preserve historical membership and expose independently advancing ages. Exact source/completeness/current-estate evidence remains explicitly unknown and captured as owner-scoped follow-up. No configured roster or fabricated estate zero.
<!-- SECTION:FINAL_SUMMARY:END -->
