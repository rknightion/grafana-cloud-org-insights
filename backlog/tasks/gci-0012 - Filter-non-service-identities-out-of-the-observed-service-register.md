---
id: GCI-0012
title: Filter non-service identities out of the observed service register
status: To Do
assignee: []
created_date: '2026-08-25 12:57'
labels:
  - pillar-k
  - coverage
  - data-quality
dependencies: []
priority: medium
type: bug
ordinal: 20000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The service register treats every distinct signal identity as a named service asset. Measured live: 18,376 discovered identities, of which the retained top-N sample of 3,566 contains at least two populations that are not application services.

## Measured contamination in the retained sample

- **363 rows (10.2%) are systemd units** - names ending `.service`, and the same pattern will catch `.slice`, `.scope`, `.socket`, `.timer`, `.mount`. These come from journal log streams, not from a deployed application.
- **A large block of rows are this platform-adjacent synthetic check identity**, one per scanned stack, matching a stable prefix pattern for k6-driven synthetic checks. They are the observability tooling observing the estate, not customer workloads, and they inflate the count by roughly one row per stack.
- **20 rows are three characters or fewer.** Names that short cannot be matched against dashboards or alerts without colliding with everything, and they are the same names that break any title-substring strategy.

## Why this matters beyond tidiness

The headline asset count is the primary business-value number on the surface. Inflating it with log-stream plumbing makes the figure indefensible the moment somebody scrolls to the register and reads the rows. It also drags the coverage-depth distribution: 97.6% of identities sit at exactly one signal, and systemd units and synthetic checks can only ever have one, so they manufacture the very shape that makes coverage look shallow.

## What to build

A classification of each discovered identity into one of three populations, published separately rather than filtered silently:

1. `application` - the asset register proper, and the only population the headline counts.
2. `platform` - synthetic checks, this platform own identities, and observability tooling. Count it, name it, keep it out of the headline.
3. `infrastructure_unit` - systemd units and equivalent host-level identities.

Publish all three counts. A silent filter would be worse than the current state: an operator who has seen the raw label values must be able to reconcile the published figure with them, and the golden rule means the classification is derived every run from live data, never a maintained exclusion list of names.

Rules must be pattern-based and identity-free - a suffix set for unit types, a documented prefix pattern for platform synthetics, a minimum length. No customer service name may enter the repository, a fixture, or a test.

## Also record

The register already discloses discovered versus retained honestly in `coverage_summary`, and the per-stack metric correctly reports DISCOVERED rather than the truncated sample. Do not change that; the truncation is not the defect here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Discovered identities are classified into application, platform and infrastructure_unit populations
- [ ] #2 All three population counts are published; none is silently filtered
- [ ] #3 The headline asset figure counts the application population only
- [ ] #4 Classification is pattern-based and derived every run, with no maintained name list
- [ ] #5 No customer identity enters the repository, fixtures or tests
- [ ] #6 Coverage-depth distribution is recomputed over the application population
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
