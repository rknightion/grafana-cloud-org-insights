---
id: GCI-0145
title: Restore CI image publication after setup-trivy install script break
status: To Do
assignee: []
created_date: '2026-11-03T23:00:00Z'
labels: []
dependencies: []
type: bug
ordinal: 183000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Since 2026-11-03 every GHCR edge, RC and release image job fails in aquasecurity/setup-trivy: it checks out Trivy's install script from upstream main (75c4dc0, 'add client option to install script', #9962) and install.sh for v0.70.0 exits 6 in under a second, before any scan. Not a finding: the v0.15.3 consumer image scanned clean locally with Trivy 0.76.1 and .trivyignore.yaml. ci-success is unaffected. Pin the install script ref, or move trivy-action/setup-trivy to a version with a fixed script, then confirm edge/RC/release publish and attach the release image for v0.15.3 if it is still missing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Edge, RC and release image jobs pass on main
- [ ] #2 v0.15.3 release image published or a documented decision not to
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
