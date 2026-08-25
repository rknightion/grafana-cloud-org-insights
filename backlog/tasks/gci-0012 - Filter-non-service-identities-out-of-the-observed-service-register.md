---
id: GCI-0012
title: Filter non-service identities out of the observed service register
status: Done
assignee:
  - '@codex'
created_date: '2026-08-25 12:57'
updated_date: '2026-08-25 15:17'
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
- [x] #1 Discovered identities are classified into application, platform and infrastructure_unit populations
- [x] #2 All three population counts are published; none is silently filtered
- [x] #3 The headline asset figure counts the application population only
- [x] #4 Classification is pattern-based and derived every run, with no maintained name list
- [x] #5 No customer identity enters the repository, fixtures or tests
- [x] #6 Coverage-depth distribution is recomputed over the application population
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Inspect the current synthetic identity conventions and add decision tests for application, platform, and infrastructure-unit classification without estate-specific names.
2. Classify every discovered identity from its live name, keep all populations visible, and restrict service/depth/score aggregates to application rows.
3. Publish bounded population counts and expose population in the service register and Coverage headline.
4. Regenerate BUDGET.md, run the full item gate and CodeRabbit, finalize, commit to main, and push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
TWO CLASSIFICATION DECISIONS, both previously unstated. These are authoritative; implement them as written.

DECISION 1 - the platform synthetic-probe pattern is the prefix `k6-synthetic-` and nothing looser.

Measured shape: this platform deploys one k6 health-check probe per stack, and its identity is
`k6-synthetic-<stack-slug>`, with `job` and `service_name` carrying the same value and exactly one
series per stack. Reach was 230 stacks with a companion health-check metric on 231.

Implement as a literal prefix match on the identity, casefolded, anchored at the start. Do NOT match a
bare `k6` substring: k6 is also a legitimate customer load-testing tool, and a substring rule would
reclassify real customer k6 workloads as platform noise. Do NOT encode any stack slug or customer
string - the slug is the variable part and must never appear in this repository.

Where the pipeline has both `job` and `service_name` for an identity, ALSO record the structural
signal that the two are equal. That equality is estate-agnostic and stronger than any name prefix, so
it is the better long-term test; the prefix is what is implementable today. If the register pipeline
only carries `service_name`, ship the prefix alone and leave a comment saying why.

Classify these as population `platform`, count them, and publish the count. They must be visible as a
named population rather than silently dropped - a reader needs to see that this platform is itself the
largest single contributor to the identity count, and a silent filter would hide a future change in
our own probe naming.

DECISION 2 - do NOT classify by identity length. There is no three-character rule, and no length rule
of any kind.

Length is the wrong instrument and this project has already measured it being wrong. On the
dashboard-matching work, requiring two or more tokens as a generic-name guard killed 45 TRUE positives
while removing 18 false ones. Short names in a real estate include genuine services, and the same
failure mode applies here: a rule that throws away every identity of three characters or fewer throws
away real applications to tidy up a metric.

Classify on EVIDENCE instead, which the register already holds:

- the structural patterns in this task already name the machine-generated class - systemd unit
  suffixes, session and user prefixes, embedded run ids, uuids;
- the platform prefix from decision 1;
- signal depth and breadth, which are already computed. An identity carrying metrics or traces, or
  more than one signal, is a service whatever its length.

An identity that matches no rule stays in the application population and is NOT reclassified on the
strength of being short. If a short-identity population turns out to be large and genuinely junk,
that is a new finding needing its own measurement and its own decision - bring it back rather than
inventing a threshold.

WHY BOTH DECISIONS LEAN THE SAME WAY: this pillar publishes a coverage denominator. Over-filtering
inflates coverage by shrinking the denominator, which is the same class of defect as the unscoring bug
GCI-0016 just fixed, only pointed the other way and harder to spot. Prefer a named, counted, visible
population over a silent drop every time.

Implemented the authoritative classifier with platform-prefix precedence, signal-evidence protection for real services, no length rule, and infrastructure classification only for remaining structural machine patterns. All identities remain visible and count exactly once; application alone feeds the headline, depth, signal, and score aggregates. Score version bumped to 3 because the aggregate population meaning changed.

Final verification: `python3 -m pytest tests -q` passed (1400 passed, 2 skipped, 6614 subtests); `tofu fmt -check -recursive terraform` passed; `tofu init -backend=false` and `tofu validate` passed in `terraform/` and `terraform/examples/standalone/`; customer-identifier working-tree/history scans and the shipped-text gate passed; `git diff --check` passed; BUDGET.md was regenerated. CodeRabbit completed with one Minor observation that the historical description still mentions a minimum-length rule. Dismissed: these authoritative notes explicitly supersede that description, preserving the correction history, and the implementation contains no identity-length classification.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Classified every discovered identity into a visible application, platform, or infrastructure-unit population using live evidence and no configured names or length threshold. Application-only headline, depth, signal, and score aggregates now use the defensible denominator; all excluded populations remain published for reconciliation. Score semantics advanced to version 3 and the new bounded population metric is budgeted. Verified by the complete pytest, OpenTofu, identifier, shipped-text, generated-budget, diff, and CodeRabbit gates.
<!-- SECTION:FINAL_SUMMARY:END -->
