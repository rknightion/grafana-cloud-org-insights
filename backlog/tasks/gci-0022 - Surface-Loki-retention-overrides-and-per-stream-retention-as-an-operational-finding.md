---
id: GCI-0022
title: >-
  Surface Loki retention overrides and per-stream retention as an operational
  finding
status: To Do
assignee: []
created_date: '2026-09-11 09:57'
labels:
  - risk
  - cost
  - retention
  - pillar-e
dependencies: []
priority: high
type: enhancement
ordinal: 30000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Grafana Cloud now lets a stack admin request a Loki retention change from the stack itself, through
the Databases Configuration app. The request opens a pull request against Grafana's own deployment
repository and engineering approves it. Retention above the plan floor is a separate billing
dimension, and a per-stream selector can multiply the retained volume of one high-cardinality stream
without moving the global figure at all. Nothing in this platform can see any of it today.

## Live-verified routes, all read-only GETs

Measured 2026-09-11 against a 286-stack organisation and a five-stack control organisation.

| Route | Identity | What it answers |
|---|---|---|
| `grafanacloud_logs_instance_limits{limit_name="retention_period"}` on `grafanacloud-usage` | none beyond the write stack | EFFECTIVE global retention per stack, nanoseconds |
| `grafanacloud_logs_instance_limits{limit_name="max_query_lookback"}` on the same datasource | none beyond the write stack | effective query lookback per stack, nanoseconds |
| `GET {stack}/api/datasources/proxy/uid/grafanacloud-logs/config/tenant/v1/limits` | stack reader, datasource proxy | full effective tenant limits as YAML, including `retention_period`, `retention_stream` and `otlp_config` |
| `GET {stack}/api/plugins/grafana-dbcfg-app/resources/v1/lokiconfigretentions` | stack reader, plugin resource route | the self-serve CHANGE REQUEST record, with author, status and the approving pull-request number |
| `GET {stack}/api/plugins/grafana-dbcfg-app/resources/v1/settings` | stack reader | `logs_tenant_id` and `logs_gcom_cluster_id` for the stack, useful for joining |
| `GET grafana.com/api/hosted-{logs,metrics,traces,profiles}/<instanceId>` | org-realm reader | an `overrides` map of limits EXPLICITLY set for that tenant, for all four signals |

## The change-request record, shape frozen from a live sibling resource

`lokiconfigretentions` is a Kubernetes-style list. An empty `items` array is the common case. The
item shape was frozen from a live `lokiconfigotlpconfigs` item, the same CRD family on the same
route, because no reachable stack carries a retention item:

```
metadata: name=<loki tenant id>, namespace=stacks-<stack id>, uid, generation,
          creationTimestamp, annotations["grafana.com/updateTimestamp"]
spec:     author, message, request_timestamp, <the limit payload>
status:   status: applied|pending|rejected, observed_generation, processed_timestamp,
          pr_info: { number: <int>, status: merged|... }
```

The retention item's payload key is NOT verified. Treat every `spec` key other than the four shared
ones as opaque: record the raw key and value, never guess a schema for it.

## Five traps, every one a case where the wrong call returns HTTP 200

- **The documented default is 30 days and every measured stack reports 31d, with no override
  anywhere.** 282 of 282 readable stacks in the large estate and 5 of 5 in the control estate are at
  exactly 31d. So "the effective value is not the documented default" is NOT evidence of an override
  and must never be used as one.
- **An empty change-request list does not mean retention is unmodified.** Engineering can apply an
  override directly, bypassing the self-serve app entirely. Two stacks were measured carrying a live
  per-stream override while their `lokiconfigretentions` list was empty. The CRD proves a self-serve
  request happened; it can never prove one did not.
- **`retention_stream` is invisible to the usage datasource.** Only five `limit_name` values exist
  estate-wide - `retention_period`, `max_query_lookback`, `max_query_series`, `ingestion_rate_mb`,
  `max_global_streams_per_user`. There is no per-stream series and there will not be one.
- **`GET /loki/api/v1/config/limits/applied` works and self-reports as deprecated**, naming the
  Databases Configuration app as its replacement. Its sibling `GET /loki/api/v1/config/limits/<name>`
  returns a plain-text `404 tenant limit not found` when the tenant never submitted a request for
  that limit - a 404 meaning "clean", not "absent route". Build on `config/tenant/v1/limits`.
- **Loki is the only signal with this API.** Tempo, Mimir and Pyroscope 404 on every `config/limits`
  path shape tried. The cross-signal equivalent is the gcom `overrides` map, and that map can also
  carry a limit explicitly set to the same value as the default, so key presence flags a no-op
  override while value comparison misses one.

## The zero-credential detector, and its measured yield

`max_query_lookback != retention_period` is a strong proxy for a per-stream retention override, and
it is visible from the `grafanacloud-usage` datasource with no collector code and no credential.

- 82 of 282 readable stacks in the large estate diverge, all of them at a lookback of 120d against a
  global retention of 31d.
- Two divergent stacks were checked directly against `config/tenant/v1/limits` and both carried a
  real `retention_stream` entry at exactly the divergent period. One non-divergent stack was checked
  as a control and carried no `retention_stream` key at all.
- Two positives and one negative support the proxy. It is not proven for all 82 and the panel must
  say so: it is a candidate count, and the collector tier is what confirms each one.

The 4-stack gap between the 286 stacks reporting logs limits and the 282 reporting retention is a
real denominator gap, so every figure carries its measured-stack denominator.

## Privacy and cardinality

- `spec.author` is a user login and `spec.message` is arbitrary customer-authored free text. Both are
  identity-bearing: view and Loki only, never a metric label. Decision recorded 2026-09-11 by Rob.
- `retention_stream[].selector` is a LogQL stream selector containing customer label names and
  values. Unbounded and identity-bearing. View column only.
- `status.pr_info.number` is a Grafana-internal pull-request number, not customer identity, and it is
  the single most useful field for a human tracing a change. It is bounded per stack but still a
  per-stack integer, so it belongs in the view rather than a metric label.
- Metrics carry only bounded aggregates: retention days per stack, a divergence flag, per-status
  counts and the measured-stack denominator.

## Deliberately out of scope

Changing retention, proposing a retention change, or touching a change request. This is a report.
The platform's HTTP client refuses every method but GET and that property stays load-bearing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Effective global retention and query lookback per stack ship as panels over grafanacloud-usage with no collector change and no credential
- [ ] #2 The lookback-divergence count is published as a CANDIDATE count with its measured-stack denominator beside it, never as a confirmed override count
- [ ] #3 A stack reader source reads config/tenant/v1/limits and publishes retention_stream entries as a view, with period, priority and selector
- [ ] #4 The lokiconfigretentions change-request record is published as a view with author, message, status, timestamps and pr_info.number
- [ ] #5 An empty change-request list is published as no-self-serve-request, never as no-override; the two states are distinct in the view and the panel
- [ ] #6 spec.author, spec.message and retention_stream[].selector never become metric labels
- [ ] #7 Unrecognised spec keys on a retention change request are recorded verbatim as opaque, never coerced into a guessed schema
- [ ] #8 Metrics are bounded aggregates only and every one is declared in budget.py CATALOGUE
- [ ] #9 A stack whose plugin route or datasource proxy fails is withheld as unreadable and never published as a structural zero
- [ ] #10 docs/traps.md records the 31d-is-not-an-override trap, the empty-CRD trap, the deprecated applied endpoint and the Loki-only scope; CAPABILITIES.md records the new routes and the identity each needs
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 just test
- [ ] #2 just tf-validate
- [ ] #3 just check-identifiers and just no-em-dashes both return clean
<!-- DOD:END -->
