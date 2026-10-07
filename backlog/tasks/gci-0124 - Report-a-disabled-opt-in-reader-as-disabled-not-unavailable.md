---
id: GCI-0124
title: 'Report a disabled opt-in reader as disabled, not unavailable'
status: To Do
assignee: []
created_date: '2026-10-07 14:48'
labels:
  - bug
dependencies: []
priority: high
ordinal: 159000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
A default-off opt-in reader that a deployment leaves disabled makes its gather function return an empty payload (scan.py gather_library_panels_inventory and siblings return {} when the reader is not enabled). hydrate.py then records the input as missing with available=False ("latest.json carries no X"), gcinsight_input_available is 0 on every tier, and the input_rule alert (min_over_time(gcinsight_input_available[6h]) < 1) fires indefinitely. Observed read-only on the customer deployment on 2026-10-07 for library_panels_inventory, which that deployment does not enable.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 A reader disabled by configuration carries a distinct 'disabled' provenance state through gather, scan output and hydration on every tier, is never counted as available, and its dependent views stay withheld (gap-is-absent preserved)
- [ ] #2 No input-unavailable alert fires for a disabled reader: either gcinsight_input_available is not emitted for it or the rule excludes it, with a fail-first test showing the old behaviour fired; an enabled reader that fails still alerts
- [ ] #3 VIEW_INPUTS re-derivation, the budget catalogue test and the dashboard coverage gate pass unchanged in meaning; just check is green
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
