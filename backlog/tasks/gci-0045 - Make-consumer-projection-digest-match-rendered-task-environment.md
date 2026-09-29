---
id: GCI-0045
title: Make consumer projection digest match rendered task environment
status: Done
assignee: []
created_date: '2026-09-24 00:16'
updated_date: '2026-09-29 20:22'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 55000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Wave 2 dev promotion reached a T2 InvalidIdentity before scanning. The manifest hashed the raw expected-retention-policy JSON string with selector before minimum_period, while Terraform jsonencode rendered the same object with minimum_period before selector. Parsed values matched, raw strings did not, so the task environment digest differed. The image was rolled back. The provisioner also exited 1 after immediate post-repair verification on two stacks, although a fresh root readback later showed all approved pairs; distinguish propagation delay from persistent failure.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 A nonempty retention policy with either input key order produces the same projection digest as the rendered ECS task environment, proven by a failing-then-passing contract test
- [x] #2 Consumer preflight catches any manifest-to-Terraform environment mismatch before an image push or apply
- [x] #3 Provisioner post-repair verification has a bounded, read-only consistency check that preserves no-remint and fails on persistent drift
- [x] #4 A separately authorized dev rollout proves provisioner and T2/T3/T1/T4 exit 0, advanced S3 heads, product routes and dashboard readback at one exact image digest
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
AC1: projection_digest is now the single digest function for manifest and task; JSON-valued keys normalise to Terraform jsonencode form (verified against tofu by an independent review). AC2: terraform_wiring_gaps runs in consumer_manifest check --terraform (so consumer-build and consumer-exec), with UNCHECKED_PROJECTED_ENV pinned by a drift test; validate() now rejects a non 1/0 DASHBOARD_DETAIL_ENABLED and differing scan/provisioner OPT_OUT. AC3: verify_reader re-probes read-only with 5/15/30s backoff only when the reader is readable and still missing pairs. AC4 is the dev rollout in progress. Review follow-ups not fixed here are logged as GCI-0048 (validate JSON values against module types).

AC4: dev rollout at image sha256:e5aced1c942cb59d2bdf328ecbddf46556394b6d9b2acccdaf6a293b76c94ca2 (sha-4b5966e), 2026-09-29. T2/T3/T1/T4 exited 0 and advanced scans/<tier>/latest.json on robk-gcinsight-dev (T2 20:08:49, T3 20:12:32, T1 20:15:31, T4 20:16:47 UTC). Provisioner exit 0, provisionable/ok=5, with product reads slo,synthetic-monitoring. All 11 dashboards HTTP 200; gcinsight-risk readback carries risk_fleet_scrape_intervals and the fast-scrape metric. Alert rules: 8, all paused and unrouted. DoD 3: no-em-dashes clean, and check-identifiers is clean on tracked files; its history leg still fails on pre-existing commits tracked by GCI-0043, so that box stays unticked.
<!-- SECTION:NOTES:END -->
