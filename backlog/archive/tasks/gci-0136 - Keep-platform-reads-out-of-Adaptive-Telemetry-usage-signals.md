---
id: GCI-0136
title: Keep platform reads out of Adaptive Telemetry usage signals
status: In Progress
assignee: []
created_date: '2026-10-13 18:31'
updated_date: '2026-10-13 18:46'
labels: []
dependencies: []
priority: high
type: task
ordinal: 176000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Imported from the unsynchronized GFMBP board, where its ID collides with the existing provenance task. Platform reads must avoid altering Adaptive Telemetry recommendations. No incident causality is established. Metrics use the documented empty __ignore_usage__ matcher; metadata counting and Logs/Traces opt-outs require evidence rather than assumptions. User explicitly prioritizes implementation and dev/customer updates on 2026-10-13.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every collector PromQL vector selector sent to an org stack carries __ignore_usage__="", with a failing reproduction and coverage guard for new metrics reads.
- [ ] #2 Classify metadata label values, series and cardinality routes against usage tracking with cited evidence, applying suppression only where supported; unresolved classification remains explicit.
- [ ] #3 Record Adaptive Logs opt-out research and affected reads, without inventing unsupported suppression.
- [ ] #4 Record Adaptive Traces opt-out research and affected reads, without inventing unsupported suppression.
- [ ] #5 CAPABILITIES.md describes proven suppression and remaining uncertainty.
- [ ] #6 Exact tested/reviewed source is released and dev/customer consumer upgrades are applied from reviewed saved plans, verified by runtime/readback and final no-change plans.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Construct the documented empty ignore-usage matcher for every collector PromQL metric literal, prove actual HTTP requests and unchanged expressions with fail-first controls; independently research metadata/Logs/Traces contracts and document unknowns. Run independent final review, CodeRabbit and just check; land exact source and verify CI/release. Upgrade dev and customer consumer source/image pairs preserving runtime policy, review separate targeted saved plans, apply exact plans, read back projections and query behavior, finish no-change plans.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Source task donor commits f2e6184b15049e15561b6ad3ef2737fa5f56f3bd and 9969571ed285f72cbb0648709736858e6de1b72d retained on GFMBP; private incident details omitted. Source refs https://github.com/grafana/mimir/pull/14474 and official understand-recommended-rules docs.

Focused code proof: original unmarked active-series request fails new HTTP-boundary guard; final 26 tests and 351 subtests pass, lint clean. All 27 expressions compare byte-identical to prior source after removing only empty ignore matcher. No general rewriting, URL parameter, new scopes or metadata suppression. Research/docs and final reviews pending.

Independent source review PASS; CodeRabbit complete0 reviewed all four changed tracked files. Actual ReadOnlyClient marked staff query returned exact200/vector with four positive rows; this is endpoint behavior, not a backend tracking counter witness. Metadata tracking remains unknown under public/private bounded research; Logs opt-out not established; current official Traces model does not use query usage. Full test portion 2747passes,27920subtests,2existing skips; final gate still finishing.

Live baseline before rollout: both deployments have five enabled schedules, zero running tasks, five consistent existing immutable images, exact task definitions and scheduler IAM captured privately. Root has exclusive serialized AWS/state/plan ownership. Rollout helper initial independent review found three classifier gaps; corrected copy-first plan identity, exact tier bindings and known/deferred IAM structure now reject prior in-memory counterexamples; delta review pending.
<!-- SECTION:NOTES:END -->
