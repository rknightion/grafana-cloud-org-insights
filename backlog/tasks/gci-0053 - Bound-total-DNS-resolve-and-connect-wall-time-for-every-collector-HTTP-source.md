---
id: GCI-0053
title: Bound total DNS resolve and connect wall time for every collector HTTP source
status: To Do
assignee: []
created_date: '2026-09-30 21:58'
labels:
  - hardening
  - collector
dependencies: []
priority: medium
type: enhancement
ordinal: 63000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Split out of GCI-0036 and GCI-0020 on 2026-09-30 by Rob. Loop3 security review found that a synchronous DNS resolution can outlast the per-request timeout, so a hung resolver can hold a tier past its budget. This applies to every source, not only SLO/Adaptive. Fresh attempt budget; loop3's four GCI-0036 attempts do not carry over.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A test with a resolver that never returns proves a source call fails within a stated total wall-time bound
- [ ] #2 The bound covers DNS resolution and TCP/TLS connect for every collector HTTP path, including the label_risk POST path
- [ ] #3 httpclient.py stays GET-only and the collector stays stdlib-only
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
