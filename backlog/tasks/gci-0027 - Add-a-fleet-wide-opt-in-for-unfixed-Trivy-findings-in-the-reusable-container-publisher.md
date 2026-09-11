---
id: GCI-0027
title: >-
  Add a fleet-wide opt-in for unfixed Trivy findings in the reusable container
  publisher
status: To Do
assignee: []
created_date: '2026-09-11 14:27'
labels:
  - ci
  - security
dependencies: []
priority: medium
type: enhancement
ordinal: 36000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The shared container-publish workflow currently gives callers no way to distinguish an unfixed operating-system finding from a fixable HIGH or CRITICAL finding. One public caller had to add eighteen expiring per-CVE exceptions to restore publishing even though every finding had an empty Fixed Version. An explicit opt-in belongs in rknightion/.github so the fleet can handle this class consistently without weakening the default gate for existing callers.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 The reusable container-publish workflow offers a documented opt-in that ignores only vulnerabilities with no upstream fix
- [ ] #2 The default remains off so existing callers keep their current Trivy gate behavior
- [ ] #3 Both architecture scans apply the option while severity, exit-code enforcement and SARIF upload remain unchanged
- [ ] #4 A tagged rknightion/.github release contains the change and identifies the callers eligible to migrate from per-CVE files
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
