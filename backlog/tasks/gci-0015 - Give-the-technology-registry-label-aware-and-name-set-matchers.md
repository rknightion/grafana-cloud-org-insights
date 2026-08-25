---
id: GCI-0015
title: Give the technology registry label-aware and name-set matchers
status: To Do
assignee: []
created_date: '2026-08-25 13:05'
labels:
  - pillar-k
  - registry
  - design
dependencies: []
priority: high
type: enhancement
ordinal: 23000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The registry matches a single metric NAME per technology. Measurement shows that constraint is now the limiting factor on classification accuracy, in two provable ways.

## 1. Some technologies are only identifiable by a LABEL, not by any name

Validating an OpenTelemetry sentinel across 270 stacks found six stacks whose OTel SDKs emit only application-specific metric names - names built from the application own domain, with no standard semconv name anywhere. Their metric-name inventory was enumerated exhaustively; there is nothing to match on. The only evidence that those stacks run an SDK at all is the `telemetry_sdk_name` / `telemetry_sdk_language` LABEL on `target_info`.

A name-only matcher therefore tops out at 20 of the 26 stacks carrying OTLP application instrumentation. The gap is not a tuning problem and cannot be closed by adding more names.

The same constraint separates instrumentation FLAVOURS that share a name. `target_info` carries `telemetry_sdk_name` values for a real SDK, for eBPF zero-code instrumentation, and for a Micrometer OTLP registry. Only the label VALUE distinguishes them, and the largest such population in the measured estate was eBPF rather than an SDK. If a technology entry needs to mean "SDK" it needs value equality, not existence.

## 2. One technology can legitimately have several equivalent names

The honest OTel sentinel is a UNION of four HTTP semconv counters - server and client, seconds and milliseconds - which together reached 20 stacks with zero false positives. Expressed as four separate registry entries, which is the only thing possible today, one instrumented stack inflates the technology count by up to four. That directly corrupts the technology-presence figure another task is introducing as a headline.

An interim workaround is already committed: the four names exist as four entries with names that say which variant each is. That is a stopgap, not the design.

## What to build

Extend the matcher vocabulary, keeping the existing `exact` and `prefix`/`suffix` forms working unchanged:

- `any_of`: a list of metric names, any one of which marks the technology present. Fixes the union case and keeps one entry per technology.
- `label`: a metric name plus a label key, and optionally a set of accepted label values. Present when a series of that metric carries a non-empty value for the key, or a value in the set. This requires the signal-inventory source to read LABEL VALUES for a named metric, not only metric names - a strictly larger read than it performs today, so cost it before committing to it.

## Constraints that must survive the change

- **Ambiguity checking must still hold.** Today two entries cannot claim one exact sentinel and `classify` raises on a name matching two entries. With `any_of` the check widens to overlapping name sets; with `label` it must also catch two entries claiming the same metric-plus-label. Validation stays strict and at load time, so a bad registry edit fails the build rather than silently reclassifying history.
- **The registry stays a versioned data file with a test**, and the test still exercises every entry against the synthetic fixture.
- **No bare first-token prefixes**, unchanged.
- **Sentinel presence is evaluated over a range window of at least ten minutes.** A sparse sentinel was measured present on 40 stacks at one instant and 188 five minutes later, against 190 over an hour. Whatever the matcher shape, the window rule applies.
- Per-stack technology detail stays a view; only bounded enums reach Mimir. Adding matcher kinds must not change that split.

## Then correct the OTel figure

Once `any_of` exists, collapse the four HTTP semconv entries into one. Once `label` exists, add the SDK entry proper and publish the honest instrumentation figures side by side rather than one blended number: SDK, SDK-equivalent, and any-OTLP-protocol. Do NOT publish `target_info` presence as OTel adoption under any matcher - it is recorded in docs/traps.md as a nine-times overstatement.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 any_of matcher implemented with load-time overlap validation
- [ ] #2 label matcher implemented, with its extra read cost measured and recorded before adoption
- [ ] #3 existing exact and prefix/suffix matchers unchanged and still tested
- [ ] #4 classify still raises on an ambiguous match under every matcher kind
- [ ] #5 the four HTTP semconv entries collapse to one once any_of exists
- [ ] #6 instrumentation reported as SDK / SDK-equivalent / any-OTLP, never as target_info presence
- [ ] #7 every entry still exercised by the synthetic fixture test
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
