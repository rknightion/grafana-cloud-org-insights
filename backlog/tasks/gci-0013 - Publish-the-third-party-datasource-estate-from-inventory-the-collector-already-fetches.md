---
id: GCI-0013
title: >-
  Publish the third-party datasource estate from inventory the collector already
  fetches
status: To Do
assignee: []
created_date: '2026-08-25 13:00'
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
- [ ] #1 Per-type datasource inventory published as a view from the existing inventory call
- [ ] #2 No new per-stack metric is emitted for datasource counts
- [ ] #3 The auto-provisioned knowledge-graph datasource is excluded from every adoption figure and the exclusion is stated
- [ ] #4 Provisioned versus actually-queried is presented as two distinct figures
- [ ] #5 Any adoption threshold uses > 1, never > 0
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
