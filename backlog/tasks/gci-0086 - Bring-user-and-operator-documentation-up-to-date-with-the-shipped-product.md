---
id: GCI-0086
title: Bring user and operator documentation up to date with the shipped product
status: Done
assignee:
  - '@loop10-root'
created_date: '2026-10-02 13:50'
updated_date: '2026-10-02 22:14'
labels:
  - docs
dependencies:
  - GCI-0085
priority: low
ordinal: 96000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Many pillars, views, reader tokens and dashboards have landed since the docs were last reviewed as a whole. Once the main feature backlog is cleared, review README, SPEC.md, CAPABILITIES.md, RUNBOOK.md, docs/ and terraform/README.md against the current code and dashboards. Run after the dashboard inventory task so the docs describe the remediated panels.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Every dashboard, view, opt-in reader token and configuration variable that ships is described in the docs, checked against the code and assembled dashboards rather than memory
- [x] #2 Statements that no longer hold (removed features, changed scopes, superseded runbook steps) are corrected or removed; BUDGET.md stays generator-only
- [x] #3 Docs build and existing doc lint pass; no customer identifier appears
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Admitted LAST after all envelope family implementations Done/Parked and dashboard0085Done. Basec4381db rootAGENTS/CAPABILITIES/LOOP now authoritative currentmain-vs-stable and parked limits. Lane owns README/SPEC/RUNBOOK/docs/terraformREADME bulk refresh, reads but doesnotedit rootstandingfiles or generatedBUDGET/tracker/code. Derive dashboard/view/token/config documentation from assembled code, validate available docs build/lint and justcheck, own landing/exactCI; docs-only skip tests added/CodeRabbit. No live publishing or new stable/deploy claims.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Docs a1 landed9d97b9820539e8d6a082725597fd799620bafbe4/tree53085d2629f9164c06a6a86db97f7079f4a3e66d. Actual publisher89views/75hydrationentries and11assembleddashboards/ninefamilytokens/config coverage;99local links/anchors clean, no repo docsbuild/lint surface so no external build invented. Final1940pass2skip8633subtests/genuine localvenv/exactCI37069051523success. CodeRabbit skipped docs-only, no tests added. Independent docsreview pending; a1infra0. Stable/main/deployment/IRMParked distinctions explicit.

Independent docsreviewFAIL9d97b982: one moderate incorrect assurance in docs/views.md usage_dormant_stacks. Actualinventorypredicate currentActiveUsers>0 and dailyUserCnt==0 aftermissing/null dailycoerced0; T2useravailability notused. Root reserves docsreview-repairr1 to correct row only/discloselimitation, no sourcechange or scope expansion; separate sourcefindingParkednotadmitted. Other14doccoverage89views/11dashboards/nine tokens reviewedpositive.

Docreview-repairr1 landed0a2964ec54109308616f076b69186eed2891df4b/tree7ff611ada8f9217a6ed91c9b0d90559e5238c500, one-rowactual dormancypredicate/missingdaily limitation only. Final1940pass2skip8633subtests/localgenuinevenv/exactCI37070613867success, docs-onlyCRskip/infra0. Source0088remainsParked and behaviorunfixed. Known reviewer resumedfocusedpass2 beforeDone; no repeatedfullreview.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Finaldocs accepted0a2964ec54109308616f076b69186eed2891df4b/tree7ff611ada8f9217a6ed91c9b0d90559e5238c500/exactCI37070613867success. Original14filepublisher89views/75deps/11assembleddashboards/nine tokens/58TFvars/projectionenvcoverage and99links reviewed; independent initialFAIL one dormancyassurance correctedone-rowr1, focusedpass2PASS/sourceunchanged. Finalgenuine-localvenv1940pass2skip8633subtests, docs-onlyCRskip/no testsadded/no externalhub/browserproof. a1/r1/infra0. Currentmain/stable5/deployment/IRMParked boundaries remainexplicit; sourcefollowup0088Parkedoutsideenvelope, no newgrant.
<!-- SECTION:FINAL_SUMMARY:END -->
