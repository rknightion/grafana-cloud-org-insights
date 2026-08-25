---
id: GCI-0008
title: Pillar K - publish the observed estate and the value it carries
status: Done
assignee: []
created_date: '2026-08-24 15:06'
updated_date: '2026-08-25 10:49'
labels:
  - pillar-k
  - coverage
  - value
dependencies: []
priority: high
type: enhancement
ordinal: 8000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Origin question, from an org senior leader, to be answered by this pillar and quoted verbatim in its dashboard banner:

> How can we expand this to show our customers which apps / infra etc are currently observed by us and how can we capture the value that we bring to the table? This could move the conversation from gaps and cost to upside potential and top line revenue growth.

Every existing pillar is gap-shaped: cost, risk, maturity and adoption all measure what is wrong or missing. Nothing in the platform assembles an ASSET REGISTER - the affirmative statement of what the estate observes and what that observation is worth. Pillar K is that surface.

## The two-part deliverable

1. **What is observed.** Named technologies, services, clusters, hosts, pods, containers, log streams, traced services and profiled services, per stack, discovered every run.
2. **What that is worth.** Coverage depth per service, outcome value (pages raised, acknowledged, resolved, ownership completeness), and unit economics with the denominators flipped from spend to things protected.

Coverage depth is the panel that does the reframe: the same table reads as "here is what we protect" and "here is the uncovered surface". The second is the expansion story without being served as a gap report.

## Data tier split, verified 2026-08-24

- **Tier 0** - `grafanacloud-usage`, already provisioned on the write stack. Answers HOW MUCH: per-stack counts with no name label. 311 grafanacloud_* metrics exist in a live org; the current dashboards read ~55. Zero credential, zero collector code, zero emitted series.
- **Tier 1/2** - the four signal databases label APIs via the org CAP. Answers WHICH: names. Same HTTP basic pattern already in collector/sources/dataplane.py, username from AUTH_FIELD.

Both are needed. Neither substitutes for the other.

## Standing constraints

- Golden rule: estate, stacks, services and technologies are all discovered every run. No configured app catalogue, no literal stack or service list.
- Names never become metric labels. Distinct Loki service_name values ranged 2 to 2,721 across six sampled stacks on one day.
- A gap is an absent series. A stack whose label read fails produces no row, never a zero-services row - otherwise the best-covered stack reads as unobserved.
- The unmatched share of any classification is published alongside it. A curated registry always lags the estate.
- Query cost lands on customer stacks. Daily cadence is accepted; four label reads per stack take 1-4s, so the estate is ~2 minutes at existing concurrency.

## Out of scope

- Synthetic Monitoring inventory (rejects an org-realm token, 500s even from an Admin SA).
- LBAC/RBAC partitioning and per-team self-service. This surface is not shown to the customer teams, so SPEC section 2 exclusion stands.
- Business-unit mapping. Stack name is the only mapping required.
- Tying observed footprint to ARR or pipeline. That join belongs in AirBud/Salesforce; this side exposes org id and stack slug as the key and stops there.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The dashboard banner quotes the origin question and the surface answers both of its halves
- [x] #2 Observed-estate figures are discovered every run with no configured stack, service or technology list
- [x] #3 Every classification publishes its unmatched share
- [x] #4 No service, metric or technology name reaches a metric label
- [x] #5 A failed per-stack label read yields an absent row, never a zero row
- [x] #6 Phase 1 ships independently and is useful with no collector change
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Deliver in dependency order through the eight tracked subtasks: ship datasource-only observed footprint first; add the bounded technology registry and explicitly-windowed four-signal inventory independently; wire the coverage composer, S3 views, bounded metrics and generated budget; build the Coverage dashboard and outcome/unit-economics surface; then validate source reconciliation and empty/absent behavior in an authorised deployment before promotion.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
All eight subtasks are complete. The final surface uses observed/observability-completeness language rather than implying protection. Names remain confined to S3 views, registry presence is discovered against each fresh estate, every classification publishes unmatched share, and failed per-stack signal reads remain absent. The banner carries the origin question verbatim. Grafana-published usage and billing metrics are read directly in dashboard panels; the collector adds only defensible bounded series and S3 registers.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Implemented and validated Pillar K as the observed-estate asset register, per-service observability-completeness surface, outcome-value view and flipped-denominator unit economics. Every child task is complete, the generated dashboard and collector contracts passed the full public gate, and live development plus billing-capable promotion checks reconciled the rendered results to their existing datasources without credential or scope changes.
<!-- SECTION:FINAL_SUMMARY:END -->
