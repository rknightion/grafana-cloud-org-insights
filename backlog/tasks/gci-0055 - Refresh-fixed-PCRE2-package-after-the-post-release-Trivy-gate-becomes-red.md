---
id: GCI-0055
title: Refresh fixed PCRE2 package after the post-release Trivy gate becomes red
status: Done
assignee:
  - '@loop5-root'
created_date: '2026-10-01 06:16'
updated_date: '2026-10-01 07:48'
labels:
  - container
  - release
dependencies: []
priority: high
type: bug
ordinal: 65000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
At final loop4 SHA542a871383eaea5d2dd5be6bb9494b14609ec887, required CI36823425388 passed but release-please edge run36823426532 and auto-rc36823566016 failed both-platform Trivy gates. New code-scanning alerts408/409 identify CVE-2026-103111 HIGH in libpcre2-8-0 10.46-1~deb13u2, fixed in 10.46-1~deb13u3. Earlier stable0.4.0/RC.11 publication was green and signed at its exact run, but that does not prove absence under a later vulnerability database. Owner closeout stopped new implementation admission; no ignore, severity, exit-code or expiry change was made. Resume from the named package/new finding, not the already repaired OpenSSL CVEs.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Both architecture images carry the fixed PCRE2 package, verified by actual package readback
- [x] #2 Real Trivy scanner and exact-SHA auto-RC publication succeed on both platforms without ignoring this fixed CVE or weakening gate policy
- [x] #3 An independently read GHCR manifest digest verifies against the pinned signing workflow, expected repository and exact source SHA
- [x] #4 Existing stable deployment exposure and upgrade choices are explicitly assessed without claiming a historical scan proves current vulnerability absence
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 just test
- [x] #2 just tf-validate
- [x] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Admitted under owner loop5 goal, 2026-10-01. Root owns tracker writes; isolated lanes own only named seams. Acceptance pending terminal evidence.

loop5 R-exp (2026-10-01 07:32-07:34Z): fresh live task-definition readbacks confirmed dev ECR digest cd5b8c4132ffaa1576051688e65e221f0696615116735b0d4dc6540d9ed4ee21 and customer baseline digest 4ad06a6b5704ba87514e5b6139c6f8565ec6b1ed7a541caefe5ac7f341f77d33. Real Trivy 0.70.0 unfiltered and repository-filtered scans both show fixed HIGH CVE-2026-103111 in PCRE2 10.46-1~deb13u2. Dev OpenSSL is fixed u3; customer also has CVE-2026-75804/CVE-2026-84782 across OpenSSL/libssl/provider u2. Selected remediation is stable 0.4.1 rollout through release/dev/customer gates; no historical scan used as current absence proof. Exact package/scanner/task evidence retained locally under loop5 R-exp. AC4 assessed; upgrade not yet deployed.

loop5 L-0055-a1 landed32258533d7e2e1fa006460224dca53135d975e98 at07:40:13Z. Root diff confirms Dockerfile-only exact PCRE2u3 fallback, upstream base unchanged, existing fixed OpenSSL pins retained. Both-architecture real package readbacku3; just check1659passed/2existing skips/7971subtests; CodeRabbit complete0findings Dockerfile reviewed; exactCI36831669276 success and auto-rc36831756263 success, jobs110269967086/110269967161 real Trivy scanner green unchanged severity/ignore policy. Failure-enforcement steps skipped, not separate passes. Known actionlint36831669905 red runner-label error resolved by next candidate, disclosed. Implementation1/review-repair0/infra0. AC3 pending independent RC digest signature witness.

loop5 R-rc accepted: v0.4.1-rc.3 annotated tag peeled to32258533d7e2e1fa006460224dca53135d975e98; independent GHCR0.4.1-rc.3 readback digestsha256:5a7665f5e21f15ae75cca814b21eff7eb21006a10e823707bbb294270a010213 arm64+amd64. Installed cosign3.1.3 verify exit0, strict pinned reusable container-publish@f32275a workflow identity/GitHub OIDC issuer/expected repository/exact sourceSHA. Initial read incorrectly included v in container tag and returned not found; actual tag derived from publication log, no publication retry. Stable release and deployment still pending.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
loop5 PCRE2 fixed by exact package pin at32258533d7e2e1fa006460224dca53135d975e98; both-platform package readbacks and unchanged Trivy gate/auto-rc36831756263 green, CI36831669276 green. RC.3 digest independently verified with strict installed cosign. Current dev/customer exposure assessed, stable0.4.1 rollout selected but not yet completed. All four task criteria proven; rollout outcome separately tracked.
<!-- SECTION:FINAL_SUMMARY:END -->
