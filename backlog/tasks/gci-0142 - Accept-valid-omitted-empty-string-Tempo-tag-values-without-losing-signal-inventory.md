---
id: GCI-0142
title: >-
  Accept valid omitted empty-string Tempo tag values without losing signal
  inventory
status: Done
assignee:
  - '@codex'
created_date: '2026-10-14 10:39'
updated_date: '2026-10-14 12:41'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 180000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Repeated exact-200 live Tempo service-name reads on dev contain 53 typed string entries, one serialized as type:string with the empty value omitted. Proto3/default jsonpb permits this shape. Current parser rejects the full stack signal inventory and dev T2 publication refuses at 5/6 coverage. Customer 1/300 failures already fall within existing 10% tolerance; no floor change is needed.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A witnessed type:string record with omitted value is accepted as empty and contributes no named service; explicit null, wrong types and malformed envelopes remain unavailable.
- [x] #2 Fail-first source-boundary regression and normal/malformed cases pass, required just check and complete CodeRabbit review pass.
- [x] #3 Signed release and dev/customer deployed source identities are verified; one fresh full-estate manual dev T2 succeeds with immutable publication, runtime, memory and bounded privacy evidence.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Apply narrowly at Tempo response parser; independently review final candidate, run required source gate, release signed two-architecture image, upgrade existing consumers preserving all policy/runtime settings, run one guarded manual dev T2, then continue previously approved customer library/auditing rollout and disable temporary dev Container Insights after proof.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Source parser/required gate/complete CodeRabbit and independent source review accepted. Signed v0.13.6 source e7910ef deployed on dev, exact saved-plan/full readback and one manual T2 exit0 with all6/6 signal inventory, immutable native publication and sampled privacy/execution-memory evidence. Customer source/image pins and ECR candidate are prepared; customer deployment/readback pending, so AC3 remains open. Evidence /Users/rob/repos/grafana-cloud-org-insights/codex/direct-20261014/tempo142/.

2026-10-14 source compatibility fix now shipped/deployed on both dev and customer at signed generic v0.13.6 source e7910efdd55738150b0d867dec816132aef468ff. Dev actual manual T2 passed healthy6/6 signal inventory with native immutable publication and qualified measured/privacy evidence; customer actual new-image provisioner started on the classified/applied/read-back six-family deployment, immutable image a45bbb954e7e7fe5796ba8ce490cba9525950e114287272b8d8fdb7ceaba6dfc. Its subsequent library repair/customer T2 remain separately owned by GCI-0132 (customer library and auditing assessment), not claimed complete here. No failure floor changed.
<!-- SECTION:NOTES:END -->
