---
id: GCI-0114
title: Decide discovery-backed per-view history and metadata gaps
status: In Progress
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 16:04'
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
- [ ] #1 Owner approves bounded input/schema scope before implementation; proposed contract proves failed inventory, removed stack, missing metadata and last-good cases without configured estate rosters.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-DOC23 schema-free build from existing supported view metadata only. Apply recorded bounded display contract to failed inventory/current-membership uncertainty, removed-stack/unknown departure, missing metadata and last-good publication/input age. Prove changing-state fixtures through actual built artifacts; no new source/schema/series/configured roster. Root records any necessary source/schema gap as a named implementable follow-up, not code here. One final gate, independent review, exact-base CodeRabbit and root land.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
D-DOC23 bounded display contract proposed by loop23 root: failed inventory means current membership unknown, never zero or a historical label union called fresh discovery; retain last-good view and expose its own timestamp. A removed-stack row is excluded only when existing reliable current inventory proves departure, otherwise label membership historical/unknown, never manufacture a configured roster. Missing per-view metadata yields unknown age/completeness, not inferred current from run time. Last-good publication time and input-observation time are distinct, with advancing staleness from existing supported metadata; measured-empty requires an available measured input, absent input is unavailable. Schema/source needed to prove membership or completeness becomes a named follow-up packet, not part of this dashboard-only build.

D-DOC23 source/schema gap recorded as GCI-0134 (approve current-estate and exact view-provenance evidence), parked for owner scope/compatibility approval. Existing snapshots and historical label_values cannot prove current identity/departure; generated_at is an envelope marker, not exact S3 upload or source observation, and generic completeness is unknown. Schema-free candidate uses runtime queries to exact existing view URLs, no roster or source field added. Actual four-state CLI artifacts and408JSONata selectors evaluated2.2.2, knownavailable ages advance while missing/unavailable ages stay unknown; independent review found no correctness blocker. No browser/deployed-plugin proof. Exactbase CodeRabbit complete0/all6files and final just check0; candidate not yet integrated.
<!-- SECTION:NOTES:END -->
