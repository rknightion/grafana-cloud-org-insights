---
id: GCI-0019
title: Publish provisioned-but-unused capability as an adoption opportunity surface
status: To Do
assignee: []
created_date: '2026-08-25 13:25'
labels:
  - pillar-k
  - value
  - adoption
dependencies: []
priority: high
type: enhancement
ordinal: 27000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Unscoring a component stops the platform reporting absent product adoption as failed coverage. That is correct but it is only half the job: it makes the number honest and then throws away the finding. The same measurement, pointed the other way, is the single clearest evangelism target the platform can hand an observability team.

## The measurement, verified against independent sources

| Capability | Provisioned | Actually used |
|---|---:|---:|
| Continuous profiling | every stack in the estate carries a Pyroscope instance | **1 stack** |
| SLOs | available everywhere | **4 stacks** |
| Traces | - | 232 stacks ingesting over 24h |
| Logs | - | 269 stacks ingesting over 24h |

Profiles confirmed three ways: the collector found one service carrying a profiles identity estate-wide; the billing datasource reported one stack with non-zero profiles usage over 24h; and the same datasource reported a Pyroscope instance provisioned on every stack. SLOs confirmed two ways: the estate metric-name sweep found `grafana_slo_*` on four stacks, and an independent SLO API census found four. Against 269 log-ingesting and 232 trace-ingesting stacks, these are outliers by three orders of magnitude rather than a measurement artefact.

## Why this is the upside half of the origin question

The origin question asked how to move the conversation from gaps and cost to upside potential. A capability that is entitled, provisioned, costed and unused on 99% of the estate is exactly that: no procurement needed, no migration, no new contract - the only missing ingredient is somebody showing a team how to switch it on. That is a conversation an observability team can act on this quarter, and the platform is uniquely placed to name which stacks to start with.

## What to build

- **A per-capability adoption row** covering profiling, SLOs, traces, span metrics, service graphs, native histograms, exemplars, IRM/OnCall, k6 and Frontend Observability. For each: provisioned or entitled, actually used, and the gap. Several of these figures already exist in the capability-adoption panels; this pulls them into one deliberate surface with a consistent denominator.
- **The named target list as a view**: which stacks carry the entitlement and show no use. That is the call list, and it is the deliverable an observability team will actually open.
- **Rank by size, not alphabetically.** A dormant two-series stack and a dormant million-series stack are not equally worth a conversation. Join the active-series figure so the list is ordered by how much telemetry is already flowing that could be profiled or given an SLO.
- **A bounded metric per capability** for the gap count so it can be trended and alerted on when it closes. Enum of capability names; no stack label, since the named detail is the view.

## Rules that must hold

- **Provisioned is not entitled and neither is paid for.** The project already refuses to read a feature flag or a quota as proof a contract includes or charges for a capability. Say "provisioned and unused"; never "paid for and wasted" without the contract in front of you.
- **A measured zero here is the finding**, unlike a structural zero elsewhere - so this surface deliberately emits zeros, in the same way the estate feature-stack metric already does. Document that exception where it is emitted so a future reader does not "fix" it.
- **Use the same unscored evidence, not a second measurement.** This surface and the coverage score must read the same inputs, or they will disagree in public. Where the score unscores `profiles` for `signal_not_in_use`, this surface counts that stack as an opportunity. One measurement, two framings.
- Denominators are windowed and population-matched, per the existing rules. Trace ingest read instantaneously is a fraction of the 24h figure.

## Wording

State it as "N stacks have no profiles" or "M stacks own zero SLOs". A bare ratio beside a capability name reads as its own opposite and has already been misread once.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Per-capability provisioned-versus-used rows for profiling, SLOs and the other listed capabilities
- [ ] #2 Named target list published as a view, ranked by active series rather than alphabetically
- [ ] #3 One bounded gap metric per capability, no stack label
- [ ] #4 Reads the same inputs as the coverage unscored reasons so the two cannot disagree
- [ ] #5 Deliberate measured zeros documented as an intentional exception to the absent-not-zero rule
- [ ] #6 No figure is described as paid for or wasted without contract evidence
- [ ] #7 Counts stated in words, never as a bare ratio beside a capability name
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
