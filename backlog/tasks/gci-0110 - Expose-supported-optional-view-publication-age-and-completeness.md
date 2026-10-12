---
id: GCI-0110
title: Expose supported optional-view publication age and completeness
status: Done
assignee:
  - '@loop23'
created_date: '2026-10-06 10:47'
updated_date: '2026-10-12 18:22'
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
ordinal: 126000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
P6: hourly composition does not make daily product observations fresh. Existing metadata must be inspected before distinguishing unavailable, disabled, measured-empty and last-good states; absent metadata is not permission to change schema.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Rendered absent, measured-empty, old last-good, partial and permission-error cases are honest; supported publication/input timestamps remain distinct, with new schema needs separately approved.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Dashboard-only existing-metadata optional-view state contract: absent/unavailable, genuinely measured-empty, old retained last-good, bounded partial and permission/transport/parse errors honestly distinct. Build on accepted per-view runtime metadata companions without source/schema change. Envelope publication marker and available-input observation/provenance age remain distinct; no exact upload/observation/completeness invention. Any missing evidence seam ties to named GCI-0134 (approve current-estate and exact view-provenance evidence) or separately named packet. Public runtime/CLI cases fail first then pass, full gate, exactbase CodeRabbit/independent review, root land.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop23: implementation attempts2, review-repair rounds0. Firstcandidate fullgate7red conflicted with olderaccepted known404 objectURL omission; retry preserved seven NON-OWNED source tests unchanged rather than relaxolderseam/expandownership. Exact4file retry25a88b3e accepted after originalred/green pluspublicfive-state CLI/readadapter/JSONata2.1proof, fullgate0, exactbaseCRcomplete0all4 and independentPASS. Knownabsent staticbuild-read/currentunknown disclosure emitsnoobjectURL/numeric/metadata query; existing/retainedexactURL runtimeages separate frommarker, partial/unavailable/disabled/no rows notcompletefreshzero. Permission401/403/transport/parse failures preserved, no deployederrorUI/browser claim. Source44946614bc186755e37697d3a6ba2ba6f9ada254 landed; composedsameSHA justcheck0 (2692pass,2 skipsnotpasses,37Tofu), exactrequiredCI38289123485 allleavessuccess. No source/schema/series/reader changes; current/exactproof gap remains GCI-0134 (approve current-estate and exact view-provenance evidence). Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop23-evidence/optional-state/.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Optional-view state disclosure is honest without weakening established absence behavior. Static absent-at-build is not currentstate; preserved last-good/input provenance and supported counts are qualified. Public local boundary and exact integrated code/CI proof passed.
<!-- SECTION:FINAL_SUMMARY:END -->
