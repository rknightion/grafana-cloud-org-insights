---
id: GCI-0087
title: Reject partial HTTP responses in the IRM integration counter source
status: Done
assignee:
  - '@loop11-root'
created_date: '2026-10-02 20:30'
updated_date: '2026-10-03 11:59'
labels:
  - source-integrity
dependencies: []
references:
  - collector/sources/irm_integrations.py
priority: medium
type: bug
ordinal: 97000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Independent loop10 review proved a real guarded-client path accepts HTTP206 with valid JSON as an available IRM integration inventory, allowing a partial subset to overwrite a last-good count. No live server emitting206 was observed. Require exactHTTP200 and preserve unavailable semantics. GCI-0074 (configured IRM integration counts) exhausted all3 review-repair rounds; this follow-up is NOT admitted and does not reset that allowance. Further execution needs explicit owner-approved allowance. Faro/ML instances are separately covered by their remaining existing repair rounds.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 With otherwise valid partial JSON, the real guarded transport and IRM source return unavailable for HTTP206; a public-boundary reproduction is seen failing before the correction.
- [x] #2 ValidHTTP200 empty and positive controls remain measured; partial input cannot publish a count or overwrite the last-good view.
- [x] #3 No permission, route, sharedResponse.ok, configuration or fixture weakening; final just check, complete CodeRabbit, independent focused review and exact-SHA CI identify the delivered correction.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop11 D-IRM11: lane a1 reproduces guarded HTTP206 red-first; source-local exact200; real T2/S3 withholding controls; final-rebase gate, CodeRabbit, exact-SHA CI, independent focused review. Two implementation and two review-repair rounds granted.
<!-- SECTION:PLAN:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Loop11 owner D-IRM11 a1 accepted: source-local exactHTTP200, real guarded206 red-first and real T2/compose/S3 withholding. Landed5e132bed12cfa71cadd4eeaad78300d454e89f6a CI37120735853success; justcheck1942pass2existing skips8633subtests, CRcomplete2/2files0findings, independentfocusedreviewPASS with parentreplay and seeded last-good preservation. Root inspected raw child tool outputs. No sharedResponse/route/permission/config/fixture change; no live206 observed. a1impl, infra0, reviewrepair0.
<!-- SECTION:FINAL_SUMMARY:END -->
