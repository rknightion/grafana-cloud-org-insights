---
id: GCI-0062
title: Give the live usage probe side-effect-free help and explicit artifact output
status: To Do
assignee: []
created_date: '2026-10-01 11:48'
labels:
  - cli
  - safety
dependencies: []
references:
  - bin/probe_usage_signals.py
priority: medium
type: bug
ordinal: 72000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The loop6 operator-doc audit found bin/probe_usage_signals.py has no argument parser or help boundary. Lines27-29 require a live context immediately, and line529 overwrites the committed testdata/usage-datasource-signals.json artifact. A --help inspection fails without a context and can perform live reads and overwrite measurements with one. This follow-up does not authorize a live probe or replacement of committed evidence.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Calling --help or invalid arguments makes no network call and writes no artifact, regardless of configured context
- [ ] #2 A live probe requires explicit context and output choices, and existing committed evidence is not overwritten implicitly
- [ ] #3 CLI-boundary proof covers help and refusal without live tenants or committed baseline replacement
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
