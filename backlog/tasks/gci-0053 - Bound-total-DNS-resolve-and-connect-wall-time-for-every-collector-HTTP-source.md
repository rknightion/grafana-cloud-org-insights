---
id: GCI-0053
title: Bound total DNS resolve and connect wall time for every collector HTTP source
status: Done
assignee:
  - '@loop4-root'
created_date: '2026-09-30 21:58'
updated_date: '2026-09-30 23:37'
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
- [x] #1 A test with a resolver that never returns proves a source call fails within a stated total wall-time bound
- [x] #2 The bound covers DNS resolution and TCP/TLS connect for every collector HTTP path, including the label_risk POST path
- [x] #3 httpclient.py stays GET-only and the collector stays stdlib-only
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
loop4 admitted 2026-09-30: root owns tracker; isolated implementation lane owns packet, gate and review. Acceptance pending exact candidate/hosted/live evidence; no completion claimed.

loop4 a1/a2 completed at root landed47f9705527eb1ca575bc0e9101922e31b763ba52, exactCI36790259578 success; stable9ba3a4c CI36790758947 success. Six actual never-return DNS modes and legacy stalled-body probes fail first then pass. CodeRabbit complete0/all7files and independent security pass2 PASS exact candidate5368a104; root patch identical and clean release gate1659pass2existing skips. All discovered source reads fenced, publishers excluded. Caller bound not hard termination/byte cap: at most32daemon reads can survive/retain transient credentials/bytes; starvation bounded by admission. No dedicated stalled TCP/TLS probe claimed. No guard/method/path/query-pin changes. Two implementation attemptsinfra0; remaining root/specialist unused.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Collector HTTP source callers now have a shared bounded complete-transport wait, including DNS, connect and body paths. Fixed worker/admission ceiling accounts for survivors. Exact-SHA CI and independent security PASS establish completion within documented caller-bound tradeoff; existing publisher and redirect behavior unchanged.
<!-- SECTION:FINAL_SUMMARY:END -->
