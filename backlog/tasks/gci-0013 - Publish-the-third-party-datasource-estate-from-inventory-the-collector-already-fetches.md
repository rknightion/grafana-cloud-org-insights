---
id: GCI-0013
title: >-
  Publish the third-party datasource estate from inventory the collector already
  fetches
status: Done
assignee:
  - '@codex'
created_date: '2026-08-25 13:00'
updated_date: '2026-08-25 17:01'
labels:
  - coverage
  - adjacent-estate
  - value
dependencies: []
priority: high
type: enhancement
ordinal: 21000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The observed-estate surface answers "what do we watch" only for telemetry this platform ingests. It says nothing about the ADJACENT observability estate - the other vendors wired into Grafana - which is the strongest available signal for where observation can carry more value.

That data is already in hand. `GET https://grafana.com/api/instances?orgId=<id>` returns `datasourceCnts` per stack, a per-TYPE breakdown, on every stack, in the same inventory call the collector already makes. Zero extra requests, zero new credential.

## Measured on a live 274-stack estate

37 distinct datasource types. Excluding the auto-provisioned knowledge-graph one, the widest reach were synthetic-monitoring, cloudwatch, infinity, prometheus and postgres; the long tail included datadog, newrelic, snowflake, elasticsearch, mongodb, azure-monitor, athena, influxdb, gitlab, github, jira, servicenow, salesforce, cloudflare, x-ray, stackdriver and logicmonitor.

Each of those is a named conversation. A stack querying another vendor through Grafana is a migration or consolidation discussion; a stack querying a warehouse is an analytics-adjacency discussion. This is the "upside potential" half of the origin question expressed in data rather than assertion.

## Do NOT collect the billing metric for this

`grafanacloud_grafana_instance_custom_datasource_count` was measured to equal `sum(datasourceCnts.values())` EXACTLY on 274 of 274 stacks. It is a strictly lossier projection - the total with the per-type detail discarded - and it would cost one series per stack to obtain a number already derivable for free. It also has a floor of ONE rather than zero: on 150 of 274 stacks the single datasource is the auto-provisioned knowledge-graph one, so `> 0` claims universal adoption of nothing. Both facts are recorded in docs/traps.md.

The one thing the metric offers that inventory cannot is a historical trend, because the billing datasource has retention and a point-in-time inventory does not. If a trend is wanted, argue for it explicitly and emit ONE estate-level series or a bounded `> 1` count - never 274 per-stack series.

## What to build

- A `views/` table: stack, datasource type, count. Names of types are a bounded-ish vocabulary but not a fixed enum, so this is a view, not a metric.
- One bounded estate metric: distinct third-party types in use, excluding the auto-provisioned one.
- A dashboard row on the coverage surface: types ranked by stacks carrying them, with the auto-provisioned one excluded and that exclusion stated in the panel description.
- Cross-reference the existing Pillar J `insights_datasource_types` view, which records which types are actually QUERIED rather than merely provisioned. Provisioned-and-never-queried is a distinct and more interesting finding than either alone; present both and say which is which.

## Constraint

Datasource type names are vendor identifiers, not customer identifiers, so they are safe to publish. Stack-to-type mapping stays in the view. No customer name, stack slug or org id enters the repository.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 Per-type datasource inventory published as a view from the existing inventory call
- [x] #2 No new per-stack metric is emitted for datasource counts
- [x] #3 The auto-provisioned knowledge-graph datasource is excluded from every adoption figure and the exclusion is stated
- [x] #4 Provisioned versus actually-queried is presented as two distinct figures
- [x] #5 Any adoption threshold uses > 1, never > 0
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Pin the inventory denominator, knowledge-graph exclusion, view-only vendor names and provisioned-versus-queried distinction with focused tests.
2. Publish a live-inventory-derived stack/type/count view and retain the ranked per-type aggregate view; replace the dynamic datasource-type metric label with scalar estate counts only.
3. Add a Coverage adjacent-estate tab showing provisioned types, the named stack register and Pillar J 24-hour queried types as distinct evidence, with a specific consolidation assessment next step.
4. Regenerate derived views and BUDGET.md, run the full repository gates and CodeRabbit, finalize Backlog, commit to main and push.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
IMPLEMENTATION EVIDENCE. The existing gcom inventory already carries datasourceCnts, so the new usage_datasource_inventory view is composed directly from the live stack set with no request, credential or configured type list. It publishes stack, datasource type and provisioned instance count. The ranked usage_plugin_adoption view remains the provisioned aggregate. Both exclude grafana-knowledgegraph-datasource because it is auto-provisioned rather than an adoption decision.

Discovered vendor type names no longer enter Mimir labels: the former gcinsight_usage_plugin_adoption{kind} series is retired. Mimir now receives only gcinsight_usage_datasource_types_distinct as the bounded estate figure. The established Synthetic Monitoring provisioned-versus-active comparison is preserved as a separate fixed scalar with no datasource label. No per-stack datasource metric or billing-datasource collection was added.

Coverage now presents the provisioned type ranking beside Pillar J datasource types actually queried in its explicit 24-hour window, then provides the named stack/type/count register. Descriptions distinguish point-in-time configuration from measured use, state the knowledge-graph exclusion and name a fundable consolidation assessment starting with the highest-reach vendor type. The Coverage freshness banner now includes the separate insights input so stale or partial query evidence cannot masquerade as current inventory.

VERIFICATION. python3 -m pytest tests -q: 1409 passed, 2 skipped, 6741 subtests. tofu fmt -check -recursive terraform passed; tofu validate passed for terraform/ and terraform/examples/standalone/ using the initialized modules. Generated BUDGET.md matches collector.emit.budget. Customer-identifier history and shipped-text gates are clean. CodeRabbit initially raised one valid test-strengthening point and one invalid generated-view claim: the latter was disproved by matching hashes over all 50 non-zero, non-excluded rows from the 40-stack compose fixture; its separate 35-type figure comes from the 271-stack evidence fixture. After strengthening the test, the final review raised 0 issues.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
Published the adjacent datasource estate from the inventory already fetched every run. Coverage now separates provisioned third-party datasource types from types actually queried over Pillar J's 24-hour window, provides the named stack/type/count consolidation call list, excludes the auto-provisioned knowledge-graph datasource from adoption, and keeps discovered vendor names in S3 rather than metric labels. The only adoption metric added is the scalar distinct-type count; no per-stack count or extra collection was introduced.
<!-- SECTION:FINAL_SUMMARY:END -->
