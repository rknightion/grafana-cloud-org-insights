---
id: GCI-0136
title: Keep platform reads out of the org's Adaptive Telemetry usage signals
status: To Do
assignee: []
created_date: '2026-10-13 17:19'
updated_date: '2026-10-13 18:58'
labels:
  - adaptive
  - cost
dependencies: []
references:
  - collector/sources/signal_inventory.py
  - collector/sources/label_inventory.py
  - collector/sources/label_risk.py
  - collector/sources/dataplane.py
  - collector/sources/loki_volume.py
  - collector/sources/capability_adoption.py
  - collector/sources/usage_insights.py
  - >-
    https://grafana.com/docs/grafana-cloud/observe-and-act/adaptive-telemetry/adaptive-metrics/manage-recommendations/understand-recommended-rules/
  - 'https://github.com/grafana/mimir/pull/14474'
priority: medium
type: task
ordinal: 171000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Platform metadata reads were observed during a bounded customer incident investigation. No causal link to changed Adaptive Telemetry recommendations is established. Customer identities and token metadata are retained privately.

Metrics: Grafana documents an empty __ignore_usage__="" matcher that preserves query results and suppresses Adaptive Metrics usage. Metadata endpoints need separate classification. Logs: research supported opt-outs and metadata tracking. Traces: establish the documented query-usage model rather than assume an opt-out exists.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Every PromQL selector the collectors send to an org stack carries __ignore_usage__="", with a test that fails if a new data-plane metrics read omits it
- [ ] #2 The metadata endpoints in use (label values with match[], series, cardinality API) are classified as counted or not counted toward Adaptive Metrics usage, with the evidence cited, and covered where the matcher is accepted
- [ ] #3 Adaptive Logs: the docs research outcome is recorded; either an opt-out exists and every Loki read uses it, or none exists and the affected reads are listed
- [ ] #4 Adaptive Traces: whether any opt-out exists is recorded; if none, the Tempo reads that could register usage are listed as a known gap
- [ ] #5 CAPABILITIES.md states what the platform does and does not do to an org's Adaptive Telemetry usage signals
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
