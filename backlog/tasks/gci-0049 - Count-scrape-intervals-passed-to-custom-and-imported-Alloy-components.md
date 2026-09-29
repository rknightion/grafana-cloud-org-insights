---
id: GCI-0049
title: Count scrape intervals passed to custom and imported Alloy components
status: To Do
assignee: []
created_date: '2026-09-29 21:55'
updated_date: '2026-09-29 21:58'
labels: []
dependencies: []
priority: high
type: bug
ordinal: 59000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
An Alloy pipeline can wrap its scrape in a custom component: a local declare block, or a module pulled in by import.git, import.http, import.file or import.string. scrape_intervals.alloy_intervals only reads interval attributes owned by built-in prometheus.* components. An invocation such as mymod.scrape "x" { scrape_interval = "15s" } is therefore ignored, and when the module comes from a remote import the pipeline reports no interval and no unparsed count: a silent miss of the exact DPM driver GCI-0046 exists to find. A local declare whose prometheus.scrape reads argument.x.value is only reported as unparsed; the value passed at the call site, or the argument default, is not followed. A read-only sweep of all 935 pipelines in a large production estate on 2026-09-29 found no imports and no declare containing a scrape, so there is no live miss today; the defect is in the parser's coverage.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 An interval-named literal on a custom or imported component invocation is counted as an interval, and a non-literal one as unparsed, proven by a failing-then-passing test
- [ ] #2 A declare whose prometheus.scrape reads argument.<name>.value resolves the call-site literal or the argument default, and stays unparsed when neither is a literal
- [ ] #3 A pipeline that uses import.* is marked as only partly visible in the risk_fleet_scrape_intervals view, so a missing interval there never reads as compliant
- [ ] #4 Pipelines with only built-in components produce the same intervals as before
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
