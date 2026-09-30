---
id: GCI-0052
title: >-
  Unblock image publishing: Trivy fails every auto-rc on two HIGH openssl CVEs
  with a Debian fix
status: To Do
assignee: []
created_date: '2026-09-30 21:58'
labels:
  - release
  - container
dependencies: []
priority: high
type: bug
ordinal: 62000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Every auto-rc and release-please image publish since 2026-09-30T12:27Z failed at 'Enforce Trivy security gate' (both linux/amd64 and linux/arm64), e.g. auto-rc 36778456497 at 53a74f3 and release-please 36778355624. Code-scanning alerts 404/405: CVE-2026-84782 and CVE-2026-75804 in openssl-provider-legacy 3.5.7-1~deb13u2, fixed in 3.5.7-1~deb13u3. So GitHub prereleases v0.4.0-rc.5..rc.10 exist with no GHCR image (rc.8 returned MANIFEST_UNKNOWN) and GCI-0030 AC5 cannot be met. Fix by taking the fixed package (base image digest bump or a pinned package upgrade), never by adding these CVEs to the Trivy ignore list while a fix exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The Trivy gate passes on both platforms in the auto-rc publish job for the landed SHA, with no new ignore entry for CVE-2026-84782 or CVE-2026-75804
- [ ] #2 The resulting RC image is present on GHCR by digest and verifies with cosign against the repository's signing identity
- [ ] #3 The fix does not weaken the gate severity, exit code or ignore-expiry policy
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
