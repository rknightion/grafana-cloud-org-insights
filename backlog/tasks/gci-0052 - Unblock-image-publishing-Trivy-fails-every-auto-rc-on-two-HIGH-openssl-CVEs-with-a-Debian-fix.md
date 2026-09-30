---
id: GCI-0052
title: >-
  Unblock image publishing: Trivy fails every auto-rc on two HIGH openssl CVEs
  with a Debian fix
status: Done
assignee:
  - '@loop4-root'
created_date: '2026-09-30 21:58'
updated_date: '2026-09-30 22:51'
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
- [x] #1 The Trivy gate passes on both platforms in the auto-rc publish job for the landed SHA, with no new ignore entry for CVE-2026-84782 or CVE-2026-75804
- [x] #2 The resulting RC image is present on GHCR by digest and verifies with cosign against the repository's signing identity
- [x] #3 The fix does not weaken the gate severity, exit code or ignore-expiry policy
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

loop4 L-0052-a1 accepted at a589c4b0aac7e369b9dccf686212a156adffd767: CI36786900500 and auto-rc36786981438 success, both platform scanner/publish jobs success. Dockerfile-only pinned fixed OpenSSL u3, no new ignores/severity/exit/expiry changes, real local both-platform Trivy clean and actual CLI help exercised. just check1649pass2existing skipped; CodeRabbit complete zero findings Dockerfile fully reviewed. Root RC.11 tag peeled to exact SHA; GHCR index sha256:19ae79eb8e5e64e764f9a56491daaadbbaa754c02864f3b4fec427c598943d6d read independently and installed cosign3.1.3 verified pinned reusable workflow identity, GitHub OIDC issuer, expected repo and exact source SHA; certificate/claims/transparency verified. Failure-only Enforce gate step skipped because scanner succeeded; not counted as a passed step. Rolling Debian exact package can retire and then build fails closed.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Fixed image publication without weakening Trivy. Both architecture jobs and exact-SHA CI/auto-rc green; independently read and verified signed RC.11 digest usable by consumers. One attempt, no infrastructure retries.
<!-- SECTION:FINAL_SUMMARY:END -->
