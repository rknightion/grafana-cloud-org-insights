---
id: GCI-0015
title: Give the technology registry label-aware and name-set matchers
status: Done
assignee:
  - '@codex'
created_date: '2026-08-25 13:05'
updated_date: '2026-08-25 18:16'
labels:
  - pillar-k
  - registry
  - design
dependencies: []
modified_files:
  - collector/technology_registry.py
  - collector/technology-registry.json
  - collector/sources/signal_inventory.py
  - collector/pillars/coverage.py
  - collector/emit/budget.py
  - bin/dashboards.py
  - BUDGET.md
  - testdata/technology-metric-names.json
  - testdata/views/coverage_metric_name_register.json
  - testdata/views/coverage_summary.json
  - testdata/views/coverage_technology_register.json
  - tests/test_technology_registry.py
  - tests/test_signal_inventory.py
  - tests/test_coverage.py
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
- [x] #1 any_of matcher implemented with load-time overlap validation
- [x] #2 label matcher implemented, with its extra read cost measured and recorded before adoption
- [x] #3 existing exact and prefix/suffix matchers unchanged and still tested
- [x] #4 classify still raises on an ambiguous match under every matcher kind
- [x] #5 the four HTTP semconv entries collapse to one once any_of exists
- [x] #6 instrumentation reported as SDK / SDK-equivalent / any-OTLP, never as target_info presence
- [x] #7 every entry still exercised by the synthetic fixture test
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Implement any_of first with failing overlap and classification tests. Measure the named-metric label-value query expansion before adopting label matching. Then add label matching with value-aware ambiguity validation, collapse the four OTel HTTP sentinels, publish SDK / SDK-equivalent / any-OTLP distinctions, and run the full repository gates.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
PRE-ADOPTION READ COST AND SEMANTICS. The first label matcher adds one unique named-metric label-values GET per successfully scanned stack: telemetry_sdk_name values restricted with match[]={__name__="target_info"}, over the same explicit 24-hour window and 100,000-value truncation guard as the existing Mimir reads. The source currently makes five Mimir GETs per successful stack, so this changes that portion from five to six requests (+20%); across the measured 270-active-stack estate the deterministic daily cost is at most 270 additional GETs. Across the whole atomic signal sweep it changes eight remote reads to nine (+12.5%). Raw label values are minimized immediately to bounded registry evidence and are never stored, logged, emitted or copied into a view.

The reporting meanings are deliberately separate. SDK means the OpenTelemetry semantic-convention reserved telemetry_sdk_name value opentelemetry. SDK-equivalent is a deduplicated application-instrumentation union of that SDK evidence, the four HTTP-semconv counters, the existing Beyla sentinel and Micrometer OTLP registry evidence using its documented io.micrometer identifier. Any OTLP remains the independent, explicitly-windowed grafanacloud_instance_active_otlp_series protocol measurement above the committed synthetic-floor threshold; transport adoption is not inferred from metric-name classification.

EVIDENCE TIGHTENING BEFORE IMPLEMENTATION. Public Beyla source defines its vendor SDK name as beyla, while Micrometer OtlpMeterRegistry sets telemetry.sdk.name to io.micrometer. SDK-equivalent therefore uses those scoped target_info label values, not beyla_internal_build_info: the build-info metric proves Beyla is running but does not prove an application was instrumented. The official SDK value remains the semantic-convention reserved opentelemetry.

IMPLEMENTED. Registry v7 adds strict any_of and label matchers while preserving exact and prefix/suffix behaviour. Name-set overlaps and duplicate metric-label claims fail at load time; runtime ambiguity remains refused across pattern, any_of, exact and label evidence. The four HTTP semantic-convention counters are one OTel HTTP technology, so one stack cannot inflate the technology count by emitting several variants.

The daily signal inventory adds exactly one scoped 24-hour Mimir label-values read per successfully scanned stack. Raw values are reduced immediately to the bounded otel_sdk registry key and sdk, beyla_ebpf or micrometer_otlp evidence enums; no source label value is stored, logged, emitted or copied to a view. Coverage publishes official SDK and deduplicated SDK-equivalent stack counts. The adjacent 24-hour Any OTLP panel remains a direct grafanacloud-usage protocol count above the committed synthetic floor.

FINAL VERIFICATION. python3 -m pytest tests -q passed with 1419 passed, 2 skipped and 6743 subtests. tofu fmt -check -recursive terraform passed; tofu init -backend=false and tofu validate passed for terraform/ and terraform/examples/standalone/. Customer-identifier working-tree and history checks passed with the local secret pattern; the shipped-text gate passed; BUDGET.md was regenerated; git diff --check passed. CodeRabbit reviewed all 15 staged files and returned zero findings.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Extended the versioned technology registry with safe name-set and scoped label matching, collapsed four equivalent OTel HTTP sentinels into one deployment, and published separate official-SDK, SDK-equivalent and independently measured OTLP-protocol figures. The extra daily read is explicitly windowed and costed, raw label values are minimized before the scan boundary, and every ambiguity, privacy and denominator decision is pinned by tests.
<!-- SECTION:FINAL_SUMMARY:END -->
