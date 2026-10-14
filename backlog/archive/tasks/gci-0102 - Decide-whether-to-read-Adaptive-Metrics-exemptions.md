---
id: GCI-0102
title: Decide whether to read Adaptive Metrics exemptions
status: Parked
assignee:
  - '@loop25-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-14 19:50'
labels:
  - owner-decision
  - cost
dependencies: []
priority: low
type: task
ordinal: 118000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Loop13 assessment gap 10: savings that ignore exemptions overstate the achievable saving (GCI-0014 notes). Needs grafana-adaptive-metrics-app.exemptions:read and plugin access pairs not approved under GCI-0041; plugin proxy returned 500 on the lab stack.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Owner decision recorded on the pairs
- [x] #2 If approved, an exact-pair staff witness precedes implementation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Loop24 decision packet: source-backed GET /api/plugin-proxy/grafana-adaptive-metrics-app/exemptions, upstream /v1/recommendations/exemptions, distinct from resources proxy. Candidate pairs exemptions:read@empty, plugin:access@empty, plugins.app:access@plugins:id:grafana-adaptive-metrics-app. Role definitions are not minimum proof. Future owner grant must explicitly name exact-pair staff witness and route, no bundles/write/delete/apply/wildcard/CAP/customer grant. Validate positive/nonempty and complete collection without seeding live objects or persisting metric/label names, reasons, IDs, creators/configuration; transient matching only, count/closed-enum output. Savings arithmetic needs expiry, suppression, match/keep/drop and recommendation-already-accounted semantics to avoid double subtraction. Recommend authorize isolated exact-pair dev witness next, not implementation yet.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Loop24 root robk witness: installed Adaptive Metrics1.20.0, resources health/control bothHTTP500; source-backed plugin-proxy exemptionsHTTP200 valid result array empty (13bytes), same-family nonexistent control404. This distinguishes route reachability from broken resource proxy, not complete empty inventory or reader-compatible minimum pairs. Existing staff Admin token; two exact read/plugin pair scopes literally observed, exact plugins.app scope not literally in response (held field in evidence means literal scope equality ONLY; wildcard/Admin authorization is not evaluated, absence does not establish denial). No reader credential use, permission/token change or grant. AC1 remains owner decision and AC2 exact-pair witness absent. Attempts0 implementation, re-witness only. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/exemptions/lane.md and /Users/rob/repos/grafana-cloud-org-insights/codex/loop24-evidence/root/exemptions-probe.json.

loop25 D-EXM25 bounded robk witness: staff Adaptive Metrics1.20.0, source-backed exemptions exact200/application-json/13bytes/result array empty; same-family nonexistent404, resource health/control both500. Isolated basicNone SA, custom role exact exemptions:read@empty plus plugin:access@empty read back; temporary token requested900s, same-token effective permissions captured, exemptions GET403/application-json/168bytes. Immediate pair sufficiency NOT established; no retry, third pair, reader-role change, implementation or customer grant. Token/assignment/role/SA teardown by recorded IDs, all three absence readbacks pass, no open mutation. Raw body/configuration/credentials not persisted. Protected metadata /Users/rob/repos/grafana-cloud-org-insights/codex/loop25-evidence/exemptions/isolated-ledger.json. Existing-reader comparison pending named credential availability.

Existing deployed robk reader comparator now captured through root serial dev read prerequisite (fresh identity, live task-definition selected SSM record in memory, no credential persistence). Six GET statuses200/200/500/500/200/404; installed1.20.0, exemptions exact200/json/13bytes/result0. Same-token effective permissions include all THREE candidate pairs, including plugins.app:access@plugins:id:grafana-adaptive-metrics-app, unlike isolated two-pair effective permission witness. This supports the third-pair hypothesis, not necessity/minimum or complete empty inventory. No role change, new reader grant, implementation or customer enablement. Full count-only evidence /Users/rob/repos/grafana-cloud-org-insights/codex/loop25-evidence/exemptions/existing-reader.json.

loop25 root probe complete, implementation attempts0 and no implementation review-repair. BasicNone/defined role for existing reader independently verified. Count-only decision packet /Users/rob/repos/grafana-cloud-org-insights/codex/loop25-evidence/exemptions/decision.md: recommend future isolated three-pair witness; immediate two-pair403 is not necessity/minimum proof. Requested900s TTL recorded; actual expiration metadata readback not captured before deletion, not claimed. Exact teardown all absent. Task finalization waits summary publication/composed gate.

loop25 final boundedwitness COMPLETE but ongoingreader/implementation approval AC1 remainsOPEN. Productcodeimplementation0; oneguarded livecreate/probe/IDteardown change-and-verify attempt1, no repair. Testedexact2pair basicNone customrole gives403 vsstaff and existingSSMreader200/json13bytes/emptyresult; existingtokenholds3candidatepairs, notisolated minimumproof or completeemptyinventory. Allnewtoken/assignment/role/SA deletedbyrecordedIDs withabsencewitness, no openmutation. RecordedexistingSA basicNone/role and tokeneffectivepermissions are independentfacts; /api/user sentinelforSAauth cannotbindprincipal, no credentialmismatch inferred. ParentparkOWNER for futureisolated3pairgrant/semanticcompleteness decision; no readerrole/policy/collector/customergrant follows. Rootcount-onlypacket /Users/rob/repos/grafana-cloud-org-insights/codex/loop25-evidence/exemptions/decision.md publishednotes through32b24de/c8; composedandexactCIgreen.

2026-10-14 owner decision: discontinue exemptions-reader work. No reader grant or implementation follows. Retain documented savings/exemption limitations and all historical exact-pair witness evidence.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Owner withdrew this optional requirement; archived without claiming implementation acceptance.
<!-- SECTION:FINAL_SUMMARY:END -->
