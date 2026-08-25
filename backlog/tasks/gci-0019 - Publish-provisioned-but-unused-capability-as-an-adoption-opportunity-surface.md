---
id: GCI-0019
title: Publish provisioned-but-unused capability as an adoption opportunity surface
status: Done
assignee:
  - '@codex'
created_date: '2026-08-25 13:25'
updated_date: '2026-08-25 16:40'
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
- [x] #1 Per-capability provisioned-versus-used rows for profiling, SLOs and the other listed capabilities
- [x] #2 Named target list published as a view, ranked by active series rather than alphabetically
- [x] #3 One bounded gap metric per capability, no stack label
- [x] #4 Reads the same inputs as the coverage unscored reasons so the two cannot disagree
- [x] #5 Deliberate measured zeros documented as an intentional exception to the absent-not-zero rule
- [x] #6 No figure is described as paid for or wasted without contract evidence
- [x] #7 Counts stated in words, never as a bare ratio beside a capability name
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Add decision tests for the write-stack-only exact datasource permission and for the new source contract, including matched windows, left-joined live inventory, denominator arithmetic, and measured-zero publication.
2. Gather a bounded per-stack capability-usage input from the write stack grafanacloud-usage datasource using its existing reader credential; hydrate it without changing other readers or widening datasource query scope.
3. Compose provisioned, used, and gap rows plus an active-series-ranked named target view; use signal_inventory as the authoritative profiles/SLO evidence shared with coverage scoring.
4. Emit one bounded capability-gap series without stack labels, add the Coverage opportunity panels and explicit deliberate-zero wording, and regenerate the derived input/view and budget artifacts.
5. Run targeted checks, the full repository gate, CodeRabbit, final diff review, Backlog finalization, commit to main, and push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AUTHORISED INPUT AND PERMISSION DECISION. The adoption surface may copy `grafanacloud-usage` data into a hydrated collector input because the S3 target register and trendable bounded gap counts unlock workflows beyond a live dashboard panel. Preserve the existing `datasources:query` grant for `datasources:uid:grafanacloud-usage-insights` on every per-stack reader. Add a second exact `datasources:query` grant for `datasources:uid:grafanacloud-usage` on the write stack only. Keep estate-wide `datasources:read` for metadata discovery; never widen `datasources:query` to `datasources:*`. Derive profiling and SLO opportunities from the same signal_inventory evidence used by the coverage score so the two public surfaces cannot disagree.

IMPLEMENTATION EVIDENCE. Added a T2-owned bounded capability_adoption input queried through the discovered write stack reader. Rate-shaped usage and population signals share an explicit 24-hour window; cumulative OnCall and current-billing-period k6 retain their native windows. The input retains only stack ids and numeric values, and its two dependent views are withheld when either capability_adoption or signal_inventory is unavailable or stale.

The coverage surface now publishes ten population/use/opportunity rows, a named opportunity register ranked by active series, and gcinsight_coverage_capability_gap with a fixed capability enum and no stack label. Profiles and SLOs reuse the exact product-use decisions used by coverage scoring. Measured zero gaps are intentionally emitted and documented as the adoption-surface exception. Every row states its population basis, window, count in words and a fundable next step; none claims entitlement, payment or waste.

The reader permission remains datasources:query on grafanacloud-usage-insights for every stack. The nominated write stack alone receives the second exact grafanacloud-usage query pair. Provisioning validates that nomination against the full live estate before any repair, removes the exact special grant from a previous write stack without tolerating any other query scope, and preserves working credentials during role repair.

VERIFICATION. python3 -m pytest tests -q: 1408 passed, 2 skipped, 6691 subtests. tofu fmt -check -recursive terraform passed. tofu init -backend=false and tofu validate passed in terraform/ and terraform/examples/standalone/. The generated BUDGET.md matches collector.emit.budget. bin/check-customer-identifiers --history and the shipped-text em-dash gate are clean. CodeRabbit first raised four edge cases; all were fixed with decision tests, and its second full review raised 0 issues.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Published a durable capability-adoption opportunity surface for profiles, SLOs, traces, span metrics, service graphs, native histograms, exemplars, IRM / OnCall, k6 and Frontend Observability. It uses the coverage score evidence where the concepts overlap, publishes every denominator and deliberate measured zero, and turns each gap into an active-series-ranked named call list with a specific fundable next step. The only new query permission is the exact grafanacloud-usage datasource scope on the discovered write stack; all other readers retain their existing usage-insights query scope.
<!-- SECTION:FINAL_SUMMARY:END -->
