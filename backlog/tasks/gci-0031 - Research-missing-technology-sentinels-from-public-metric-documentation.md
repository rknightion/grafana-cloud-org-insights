---
id: GCI-0031
title: Research missing technology sentinels from public metric documentation
status: Done
assignee: []
created_date: '2026-09-23 11:53'
updated_date: '2026-09-23 18:49'
labels:
  - technology-registry
  - documentation
dependencies: []
priority: medium
type: task
ordinal: 40000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The registry still lacks unambiguous sentinels for technologies absent from the observed corpus. A short-lived lab deployment approach was stopped after an admission-controller side effect, so future candidates should be researched from public primary documentation instead of deploying workloads. Treat documentation as evidence for a documented metric name and version, not as proof that a particular estate emits it.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 For each candidate technology, record an official documentation URL, exact metric name, description, component or exporter that emits it, and version scope.
- [x] #2 Distinguish server metrics from similarly named client, collector or exporter metrics; leave a technology without a defensible always-present sentinel unregistered and state why.
- [x] #3 Add accepted documented sentinels to the registry with provenance and focused fixtures, without any lab deployment or customer identifiers.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 1 source commit 579197b26afae694bc7667b256bc06e3fd48640f added ClickHouseAsyncMetrics_Uptime and CockroachDB sql_count with official documentation provenance and focused fixtures. Cilium and Istio candidates remain unregistered with reasons. Isolated clean-checkout just test: 1494 passed, 2 skipped, 7294 subtests. CodeRabbit review: zero findings. Hosted CI 35905077040 at the exact SHA succeeded: pytest, tofu validate, identifier scan, no-em-dashes and ci-success all passed. The local just check stopped only because the private identifier pattern is unavailable in this checkout; hosted CI supplied it.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Documented two server-side technology sentinels and their version limits, left unsupported Cilium/Istio candidates unregistered, and verified source and hosted gates at 579197b.
<!-- SECTION:FINAL_SUMMARY:END -->
