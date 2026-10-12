---
id: GCI-0112
title: Decide the OnCall matched-window engagement contract
status: Done
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 13:44'
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
ordinal: 128000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
N1: gauge group populations and seven-day histogram observations do not establish a matched acknowledgement-share denominator. Existing ratios may imply an unsupported cohort or causal outcome. No new live research or semantic change is granted by this task.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Owner decides separately qualified counts versus matched-cohort research; any retained quantitative ratio has independent population/window evidence, otherwise it is withheld without calling unknown zero.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
D-DOC23 build: retain separately qualified OnCall group counts and 7d response bands, withhold unmatched acknowledgement ratios with reason. Implement rendered dashboard contract, gate just check, independent review and root-only land.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: implementation attempts1, review-repair rounds0. Exact candidate78daf4b accepted after discriminating fail-first, real CLI-built dashboard readbacks, independent reviewer PASS and CodeRabbit complete0/all4files. Root landed4310826aabb10f4c78e56f58e73611aa2fc0ea25; composed just check0 (2614 passed,2 existing skips not passes,37Tofu) and exact required CI38254439412 all leaves success. Four unsupported shares are query-free withheld explanations, counts and7d bands separately qualified; layout unchanged. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/oncall/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
D-DOC23 applied: unmatched OnCall acknowledgement shares withheld rather than numeric zero or unqualified ratio. Count/window contract exercised through actual built artifacts; exact integrated local and required CI proof retained. No source, new series or live deployment change.
<!-- SECTION:FINAL_SUMMARY:END -->
