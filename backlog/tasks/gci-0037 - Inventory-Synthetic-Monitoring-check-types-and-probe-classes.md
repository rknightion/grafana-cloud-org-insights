---
id: GCI-0037
title: Inventory Synthetic Monitoring check types and probe classes
status: Parked
assignee:
  - '@loop10-root'
created_date: '2026-09-23 18:35'
updated_date: '2026-10-02 19:09'
labels:
  - feature-usage
  - follow-on
dependencies: []
references:
  - backlog/docs/doc-0006 - Feature-usage-observability-matrix.md
priority: medium
type: enhancement
ordinal: 47000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Rank 4 - high value, moderate access and privacy cost. The current usage metric proves execution quantities but not typed check inventory. Resolve the documented SM backend address and a safe read credential after the separate scope decision. Proposed new emitted series: 0; check and probe counts are point-in-time views.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 GET check and probe routes are verified on more than one stack before use
- [x] #2 Output retains only bounded check type and public/private probe class, not target URLs or scripts
- [x] #3 Unavailable coverage is absent, not zero
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Root records S-SM exception and staff proxy shapes. L-sm implements exact opt-in scopes and minimised counts, offline proofs, gate/review/CI. Root security review and two-stack dev runtime proof.

Implement loop10 L-sm2 frozen scope at attempt a2; final-rebase gate/CodeRabbit/exact CI lane-owned; root security review and dev counts on two stacks required for AC1.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Parked at Wave 1 boundary pending GCI-0041 reader scope decision and exact safe read-route verification. No new scope, policy or credential was granted during research.

Loop9 L-sm-a1 contract-blocked without code changes: frozen absent-token deselection permits datasource discovery only after exact held SM UID is known, while permission responses do not encode plugin type. Two identical extra-query roles may point to SM vs unrelated datasource; datasource lookup is required to distinguish but forbidden in unrelated case. Guarded non-baseline candidate discovery would change explicit zero-call predicate and needs owner clarification. No golden, gate, CI, live AC or capability claimed. Root retains exact approved scope record as future policy, not implemented capability.

Loop10 a2 recommission: a1 blocked on contradictory absent-token discovery predicate -> owner S-SM(e') permits one bounded discovery only when non-baseline query held, root boundary pushed 82743e3 -> recording-fake zero calls for v0.4.3-correct combinations and one discovery for held non-baseline query -> a2 reserved, a3/a4 remain.

Loop10 a2 consumed infra0, blocked on correct write-stack grafanacloud-usage query vs sole-baseline discovery contradiction. Root current-loop e-prime clarification excludes only already-approved telemetry pairs (usage-insights everywhere, usage only write_stack=True), preserving v0.4.3 desired/removable/dangerous rules and zero calls for all correct roles. Discriminator original-source golden over both write_stack states and all combinations + recording fake. a3 root rescue reserved; a4 remains.

Loop10 a3 candidate exacttreec8f86607c3b244e8c6022005a8b0fe8071f071f5, integratedgate1705pass2skips8066subtests, twoCodeRabbitcomplete26/26 rounds with unsafe UID-retirement/empty-optout suggestions rejected and genuineknownabsence/bootstrap/inputage/repeateddiscovery defects fixed. Rescueguard blocked push beforeexecution; root amendedcandidateboundary and landedEXACTtree a7a1199942c39b5a8e6785179873c99b97907cf4, CI37025706030success. a1/a2/a3 consumed, infra0,a4unused; independentsecurity/live2stackproof stillowed, AC1 notchecked.

R-sec round1 FAIL at a7a1199: actual stdlib cross-origin redirect on new discovery leaked fake-admin and forged validUID into querygrant in offline real ensure_role/reader_policy proof; no live disclosure observed. Root releaseblocked; review-repair GCI-0037-r1 reserved (implementation a4 remains). Bounded fix validated inventory HTTPSorigin and no-redirect bounded discovery GET, no broad legacytransport rewrite, process-edge regression no secondrequest/no grant/no credentialforwarding. R-sec independently regenerated8legacygoldens and135tests passed; prior CRfalsemajor dispositions supported.

Reviewrepairr1 consumes1round infra0; real redirectedUIDgrant redrepro fixed via validated originalHTTPSinventoryURL guardedboundedno-redirect discoveryGET only. Finalgate1707pass2skips8066subtests/CRcomplete2files0findings. Root verified patch0ff5c95e3011641e91752c0d66e525d5061e4b9a1e8ebd3310d37fef0c435252/treeb3e2ace42b7cd98b16d2fb3194a77e95b74780c4 and landedexactaf5b2a1be7a8065a3baacc10b76cd040e6b5e87b; CIpending/R-sec round2recheck active. No observed livecredentialleak, legacytransport outsidenewdiscovery unchanged.

IndependentR-sec focusedround2 PASS exactaf5b2a1:6candidatefunctions loadedfromexactgitobjects passed, negativecontrolpredecessorfailedarbitrarygrant; no newmustfix. ExactCI37037362309success. Review1HIGHclosed; rawround1/2 appendedmanagedartifact preserved plusrootdistinct R-sec/return-r2.md. Live2stack/devproof stillowed.

Loop10 code/release stable0.5.0 and exactCI/securityproved, but taskAC1 andgoalR-dev remainPARKED: AWS SSOexpired beforedevconsumer/provisioner/deploy, no freshdeployedreader two-stack counts. Archive targetcandidate/restoredownlocalprep exactproven0.4.4. a1/a2/a3implementationconsumed/r1reviewrepair/infra0/a4unused; resumeexternalauthreconcile+freshtwo-stackreaderproof, never substituteAdminhistoricalshapes ormintworkingcredential.
<!-- SECTION:NOTES:END -->
