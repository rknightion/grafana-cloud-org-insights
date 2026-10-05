---
id: GCI-0093
title: Define and fence future-dated hydrated scan inputs
status: Parked
assignee: []
created_date: '2026-10-05 21:51'
labels:
  - hydration
  - follow-on
dependencies: []
priority: medium
type: bug
ordinal: 109000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Independent loop12 library security review corrected a worker overclaim: collector/emit/hydrate.py rejects missing or too-old ages but admits negative ages; the library tests do not exercise future timestamps. This is pre-existing, not introduced or repaired by the library integration. A future-dated input policy and public-boundary reproduction are needed so future timestamps cannot manufacture freshness. This serves rollout provenance reliability but is outside the accepted schema/null repair packet. Requires an owner-graded follow-up scope and attempt allowance; no loop12 ceiling reset or live deployment is authorized here.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Define future-dated owner-input handling and any justified clock-skew tolerance without altering schema-version or own-input hydration rules
- [ ] #2 Observe a failing public hydration/compose reproduction, then prove unavailable future input preserves last-good output and honest provenance without weakening exhaustive resource-bounded derivation
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
