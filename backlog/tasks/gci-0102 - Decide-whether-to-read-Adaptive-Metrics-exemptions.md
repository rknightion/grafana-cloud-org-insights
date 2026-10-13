---
id: GCI-0102
title: Decide whether to read Adaptive Metrics exemptions
status: In Progress
assignee:
  - '@loop25-root'
created_date: '2026-10-06 10:23'
updated_date: '2026-10-13 08:50'
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
- [ ] #2 If approved, an exact-pair staff witness precedes implementation
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
<!-- SECTION:NOTES:END -->
