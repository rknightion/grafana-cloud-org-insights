---
id: GCI-0075
title: Count IRM alert groups through the projected stats route
status: Done
assignee:
  - '@loop11-root'
created_date: '2026-10-02 09:25'
updated_date: '2026-10-03 14:43'
labels:
  - feature-usage
  - scope-decision
dependencies: []
references:
  - codex/loop9-evidence/L-fam/packets.md
priority: medium
type: task
ordinal: 85000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Exact declared reader pairs returned403 historically while Admin succeeded; diagnose without silently adding permissions. Capped values remain lower bounds and API-default window is not lifetime inventory. Owner decision GCI-0041 (product read scope approval) is conditional future authority, not a customer grant or loop9 implementation admission. Packet 2 in codex/loop9-evidence/L-fam/packets.md (sha256 e46afeb70fca8cd53ee0843c898c810a80cc05bc4238db02d8df2c6310eac6ad) holds exact routes/pairs, exclusions and outstanding witnesses.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Fresh authorised dev evidence establishes exact action/scope pairs, permitted route/method and complete count visibility, or records the precise blocker without widening authority
- [x] #2 Any implemented source emits counts and bounded enums only; sensitive sentinels are absent from payloads, logs, errors and persisted envelopes; unavailable coverage remains absent
- [x] #3 Any implementation follows fresh inventory, exact selected read boundaries and offline public-boundary proofs with final just check and hosted CI; conditional blockers in the packet are resolved before build
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop11 R-wit11 exact declared alert-groups:read empty plusIRMplugin access, basicNone GET /api/plugins/grafana-irm-app/resources/alertgroups/stats/ freshHTTP200 count14 equalAdmin, shape count canonicaldecimalstring. Historical403 no longer reproduced on recorded actualstats route. Build becomes ready only after prior family lands (sharedfilemutex); T2 count/relation/api_default_window only, no lifetime/statussum/contentlist/extra pair. Defaultoff future token, no newseries.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Evidence codex/loop11-evidence/R-wit/GCI-0075/ledger.json positive; SA70 token80 roleag03zv2yvcow0d recorded-IDdeleted200/404/postlistsabsent. Implementationnotyetadmitted, waits L-fam-GCI-0083 sharedfiles; no grant widened.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Loop11 accepted9c04eeaddccec8b2895f6786bd2650df0c8d566d CI37129055777allfourjobs success, justcheck1980pass2skips8763subtests/TFidentifierclean, CR18/18complete0directevent, independentAstraPASS133tests/no skips+1536combination check+6adversarial cases. Defaultoffirm-alert-groups exact2pairs/GETstats no params, solecountcanonicalASCIIstring max18digits; pluslowerboundnotexact/APIdefaultwindownotlifetime; count/relation/populationonly, malformed/206unknown/lastgood. RootNone/Adminstats200count14/IDteardown freshpositivewitness. a1impl, infra1malformedrootprompttruncatedbeforeimplementation thencompletebriefnativecontinuation; reviewrepair0. InitialImportErrorred provesmissingfeaturestructuralonly, noteach206branchred; dependencyderivationred meaningful. INPUT28+8plannedprovenanceseries/zero newproductmetrics. Notinsignedv0.6orcustomer/devreaderset.
<!-- SECTION:FINAL_SUMMARY:END -->
