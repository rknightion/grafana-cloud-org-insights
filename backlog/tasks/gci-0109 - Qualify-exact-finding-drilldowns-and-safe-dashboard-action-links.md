---
id: GCI-0109
title: Qualify exact finding drilldowns and safe dashboard action links
status: Done
assignee:
  - '@codex'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-13 16:07'
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
ordinal: 125000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
P5: finding detail conditions can differ from their headline counts, and numeric-only registers lack reliable navigation. Link identity schemas and privacy need independent verification; no inferred hostnames or sensitive URL values.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Each admitted link resolves only from existing permitted identity fields and carries intended selection/time; detail populations match finding predicates. Missing identity never invents a destination.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement only frozen D-LINK23 section3 links1-10 after the ownership prerequisite; explicit missing-slug no-link and unmatched stack_id row-retention/no-link before conditional7, All/single/multi plus gcinsight/consumer prefix and time proof, final assembled target IDs, predicates exactly SPECS. Never hostname inference, email/uid/label/service/cluster/raw evidence in URLs; no new source/schema/identity.

2026-10-13 direct-main follow-through: ownership prerequisite accepted at 7b282d0 after full local gate and two reviews. Implement frozen ten safe-link families serially using final assembled target IDs, permitted existing stack identity and time context. Real Grafana link interpolation/rendering must prove missing/null/empty identity has no destination; blank URL alone is insufficient. Preserve unmatched retention identities with no link and exact FindingSpec predicates; no new source/schema/sensitive URL fields. Root owns final review, full gate, commit/push and CI.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop23 zero implementation attempts: dependency park. Frozen prerequisite GCI-0122 (per-tab field and enum ownership) reached its ceiling without acceptance, so no safe serial source/ownership contract was released. Resume after that task is accepted; no links implemented by bypassing dependency. Existing section1 static canonical links are already accepted, but do not fulfill all section3 actions.

2026-10-13 direct-main completion: all ten admitted link families use assembled targets, existing slug and time. Single-fetch linked/unlinked partitions retain malformed/missing rows; exact FindingSpec populations preserved. Real pinned Grafana12.2 TemplateSrv/LinkSrv, converters, transformations, link supplier and cell helper prove both prefixes and All/single/multi; eight URL mutations reject. Real AI converter counterexample exposed legend fallback to numeric stack_id; corrected to actual slug labels, missing rows retain visible unlinked Stack ID. Runtime150-row proof retains global top100 and37% qualified unit display. CodeRabbit two major absent-optional-panel crashes reproduced/fixed; required mistakes still fail,12present artifacts byte-identical. Independent security final and optional delta PASS; CodeRabbit full complete2major then delta complete0/all3correctedfiles. Final just check exit0:2746Python passes,27916subtests,2skips;37Tofu passes; identifier current/history/text/format clean. Changed attribution/ranking tests enforce effective alias/unit and global pre-partition cap; no weakened behavior. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261013/drilldowns/report.md and post-review-just-check-result.json. No deployed-browser/live-tenant claim.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented safe stack-only drilldowns with real Grafana URL processing, exact finding predicates, row-preserving missing identity behavior and optional endpoint guards. Full local gate and reviewed corrections pass; no deployment claimed.
<!-- SECTION:FINAL_SUMMARY:END -->
