---
id: GCI-0055
title: Refresh fixed PCRE2 package after the post-release Trivy gate becomes red
status: Parked
assignee: []
created_date: '2026-10-01 06:16'
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
- [ ] #1 Both architecture images carry the fixed PCRE2 package, verified by actual package readback
- [ ] #2 Real Trivy scanner and exact-SHA auto-RC publication succeed on both platforms without ignoring this fixed CVE or weakening gate policy
- [ ] #3 An independently read GHCR manifest digest verifies against the pinned signing workflow, expected repository and exact source SHA
- [ ] #4 Existing stable deployment exposure and upgrade choices are explicitly assessed without claiming a historical scan proves current vulnerability absence
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
