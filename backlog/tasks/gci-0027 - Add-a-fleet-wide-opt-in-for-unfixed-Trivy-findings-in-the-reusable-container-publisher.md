---
id: GCI-0027
title: >-
  Add a fleet-wide opt-in for unfixed Trivy findings in the reusable container
  publisher
status: Done
assignee: []
created_date: '2026-09-11 14:27'
updated_date: '2026-09-23 18:44'
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
- [x] #1 The reusable container-publish workflow offers a documented opt-in that ignores only vulnerabilities with no upstream fix
- [x] #2 The default remains off so existing callers keep their current Trivy gate behavior
- [x] #3 Both architecture scans apply the option while severity, exit-code enforcement and SARIF upload remain unchanged
- [x] #4 A tagged rknightion/.github release contains the change and identifies the callers eligible to migrate from per-CVE files
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 1: rknightion/.github commit e937a74 adds default-off trivy-ignore-unfixed to the shared matrix scan and documents it. Local just check passed. CodeRabbit first pass identified Trivy action default-value precedence; explicit TRIVY_IGNORE_UNFIXED env was added and second review completed with zero findings. Hosted ci run 35903110979 succeeded at e937a74. Release PR 97 merged at 8d14ada; v1.24.0 tag was not yet visible at this note. Code search found two eligible callers with per-CVE files: this product repo and meraki-dashboard-exporter. Eligibility means review for migration, not automatic removal of every exception: the latter file also covers findings whose packages are absent from the built image. No caller was migrated in this wave.

Release readback: v1.24.0 published 2026-09-23T18:37:42Z at tag/ref 8d14adaa295c4a7670b1d4e744b070955b710598, after release-please workflow 35903747229 succeeded. Shared workflow CI 35903110979 was success at e937a74cdf1ef5bc95664b8302c3f80148e90f35. The generic Definition of Done recipes on this task refer to the product repository and are not .github workflow checks; .github just check and hosted CI were run instead.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Released default-off trivy-ignore-unfixed in rknightion/.github v1.24.0. Explicit environment precedence keeps false effective even with a Trivy config file. Both architecture scans retain severity, exit code and SARIF behavior. Eligible per-CVE callers are grafana-cloud-org-insights and meraki-dashboard-exporter; neither was migrated in this wave.
<!-- SECTION:FINAL_SUMMARY:END -->
