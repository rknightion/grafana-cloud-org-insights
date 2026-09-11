---
id: GCI-0024
title: >-
  Unblock container publishing - Trivy fails the gate on base-image CVEs that
  have no upstream fix
status: In Progress
assignee:
  - '@codex'
created_date: '2026-09-11 14:14'
updated_date: '2026-09-11 14:41'
labels:
  - ci
  - security
  - release
dependencies: []
priority: high
type: bug
ordinal: 33000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
No container image has been published since 2026-09-01. Five RC prereleases (`v0.3.0-rc.30` through `rc.34`) exist as GitHub releases with no image behind them, and the `edge` publish on every push to `main` fails the same way.

## What actually happens

`release-please` and `auto-rc` both call `./.github/workflows/publish.yml`, which calls `rknightion/.github/.github/workflows/container-publish.yml@v1.21.0`. Trivy runs with `severity: CRITICAL,HIGH` and `exit-code: "1"`, finds unaccepted findings, and the reusable's `Enforce Trivy security gate` step fails the job with:

```
Trivy reported a scanner error or an unaccepted HIGH/CRITICAL finding
```

Both platforms fail identically. The scanner itself is healthy - it initialises, detects `debian 13.6`, scans 89 OS packages and one language-specific file, and writes its SARIF. This is the gate working, not the scanner breaking.

## The traps

**This is not the OCI-tar bug and not a stale pin.** The caller is already on `v1.21.0`, the newest release of the reusable, so there is no version bump to make.

**A base-image digest bump cannot fix it.** The Dockerfile pins `python:3.14-slim@sha256:cad9a2c871761c413caa6fdd6441c783451e740a48aaeba60ae62a8b53525ef6`, and that digest IS the current upstream `python:3.14-slim`. Renovate has nothing to offer and no PR open.

**Every finding is unfixed upstream.** All eighteen HIGH/CRITICAL alerts report an empty `Fixed Version`: `perl-base` (four, three of them CRITICAL), `util-linux` (four), `perl-Archive-Tar`, `perl-IO-Compress`, `Storable`, `libsqlite3-0` (two), `ncurses-bin`, `libudev1`, `gzip`, `libacl1`. Waiting for Debian is not a repair on any useful timescale.

## The decision, settled 2026-09-11

Add a reviewed Trivy ignore file to this repository and pass it through the reusable's existing `trivy-ignore-file` input. Per-CVE, with an expiry date on each entry so the finding returns rather than being suppressed forever.

Rejected: adding an `ignore-unfixed` input to `rknightion/.github` container-publish. That is the structurally better answer because unfixed-CVE noise is fleet-wide, and it should be filed separately - but it blocks this repository behind a cross-repo release and would change behaviour for eleven other callers.

Rejected: leaving the gate red. RC tags keep being cut with nothing shippable behind them.

## Constraints

- **Do not weaken the gate's severity or exit code, and do not disable Trivy.** The `trivy` and `trivy-upload-sarif` inputs both stay `true`.
- **Do not add a blanket ignore.** Each entry names one CVE, states that no fix is available, and carries an expiry.
- **Every entry needs an expiry date** so a CVE that gains a fix re-fails the gate instead of staying suppressed.
- **The ignore file is shipped text**, so it passes `just no-em-dashes` and the customer-identifier gate.
- Verify the repair by observing an actual image published to GHCR at the new revision, not by a green run alone. A green `auto-rc` that skipped the publish is not evidence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reviewed Trivy ignore file exists in the repository, one entry per CVE, each naming that no upstream fix is available
- [ ] #2 Every entry carries an expiry date so the finding re-fails the gate once it lapses
- [ ] #3 publish.yml passes the file through container-publish's trivy-ignore-file input
- [ ] #4 Trivy still runs with CRITICAL,HIGH and exit-code 1, and SARIF upload stays enabled
- [ ] #5 An image is observed published to GHCR at the repaired revision, not merely a green workflow run
- [ ] #6 A separate tracker entry records the rejected fleet-wide ignore-unfixed input for rknightion/.github
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Reconfirm the current failed publish evidence, exact CVE set, reusable input contract, and current base-image status.
2. Add a reviewed per-CVE Trivy ignore file with an expiry and no-fix rationale for every entry, then wire it through publish.yml without weakening Trivy or SARIF.
3. Validate the declarative change with workflow parsing, actionlint, identifier and dash gates; skip a unit test because this is declarative configuration.
4. Commit only the task files to main, push, and verify a GHCR image exists for the repaired revision.
5. Create the separate fleet-wide follow-up task, then finalize GCI-0024 through the CLI against objective evidence.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
The first hosted repair attempt at 3215d3d proved the 18 per-CVE rules were loaded: all unfixed operating-system findings were suppressed, but the gate still found two fixable HIGH findings in pip vendor metadata from the pinned Python base. The collector is stdlib-only and never installs Python packages, so the follow-up removes pip and ensurepip from the runtime image. Local ARM64 proof: collector --help exits 0, aws --version exits 0, Python imports neither pip nor ensurepip, and Trivy 0.70.0 reports zero HIGH/CRITICAL findings with the reviewed ignore file. CodeRabbit reviewed Dockerfile and returned 0 findings.
<!-- SECTION:NOTES:END -->
