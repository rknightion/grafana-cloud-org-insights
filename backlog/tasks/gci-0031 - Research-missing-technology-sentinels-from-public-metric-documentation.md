---
id: GCI-0031
title: Research missing technology sentinels from public metric documentation
status: To Do
assignee: []
created_date: '2026-09-23 11:53'
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
- [ ] #1 For each candidate technology, record an official documentation URL, exact metric name, description, component or exporter that emits it, and version scope.
- [ ] #2 Distinguish server metrics from similarly named client, collector or exporter metrics; leave a technology without a defensible always-present sentinel unregistered and state why.
- [ ] #3 Add accepted documented sentinels to the registry with provenance and focused fixtures, without any lab deployment or customer identifiers.
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
