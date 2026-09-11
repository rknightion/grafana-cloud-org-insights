---
id: GCI-0020
title: Publish Adaptive Traces enablement and sampling savings
status: Parked
assignee:
  - '@codex'
created_date: '2026-08-25 14:11'
updated_date: '2026-09-11 10:06'
labels:
  - cost
  - value
  - adaptive-traces
dependencies: []
priority: high
type: enhancement
ordinal: 28000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
Adaptive Traces is measurable TODAY with no collector code and no credential. `grafanacloud-usage` carries eight `..._adaptivetraces_*` series, all verified present:

```
grafanacloud_traces_instance_adaptivetraces_bytes_received_per_second
grafanacloud_traces_instance_adaptivetraces_bytes_dropped_per_second
grafanacloud_traces_instance_adaptivetraces_spans_received_total:rate5m
grafanacloud_traces_instance_adaptivetraces_discarded_spans_total:rate5m
grafanacloud_traces_instance_adaptivetraces_global_sampled_traces_total:rate5m
grafanacloud_traces_instance_adaptivetraces_policy_sampled_bytes_total:rate5m
grafanacloud_traces_instance_adaptivetraces_policy_sampled_spans_total:rate5m
grafanacloud_traces_instance_adaptivetraces_policy_sampled_traces_total:rate5m
```

## Measured on a live 270-stack estate

- **Two stacks** have Adaptive Traces reporting at all. Both are non-zero and both are actively dropping.
- On those two stacks it drops **63% of the trace bytes it receives**. That is by far the largest single-lever reduction ratio this platform has measured anywhere.
- About 10,400 spans per second discarded, and roughly 49 KB/s of the estate total trace ingest of about 4.8 MB/s, so around 1% of estate trace volume - because only two stacks use it.
- **Nine distinct sampling policies** across those two stacks, with recognisable names: keep all traces with errors, sample slow traces, sample unique traces, percentage sampling by count and by volume, plus one custom policy.

The story writes itself: a lever that removes roughly two thirds of trace bytes where it is switched on, switched on by two stacks out of two hundred and seventy. This belongs on the adoption-opportunity surface as much as the cost one.

## The `policy` label is identity-bearing and semi-unbounded

Its value is shaped `<instance-id>.<human-authored policy name>/<uuid>`. That means it carries customer-authored text and a uuid, so it is **never a metric label in our output** - policy detail is a view column only, exactly as metric names and service names already are. It is also a good live example for the label-hygiene detector: a uuid inside a label value is the unbounded-cardinality pattern that detector is meant to catch.

## Build it as panels first

Everything above is a panel on a datasource already provisioned on the write stack. No collector source, no credential, no emitted series. Do that first and separately from anything needing the stack reader.

- Enablement: stacks reporting Adaptive Traces, against stacks ingesting traces at all as the denominator. Both windowed over the same range; trace ingest is bursty and an instant denominator understates it badly.
- Reduction: dropped bytes over received bytes, on the enabled population only. Never divide by the estate trace total and call it an estate saving - state the enabled denominator beside it.
- Per-policy breakdown from the `policy` label, in a table.
- Discarded spans as its own figure. Discarded is not the same as sampled-out and the two must not be summed.

## What the newly granted stack actions add

The reader now carries `grafana-adaptivetraces-app.policies:read`, `.recommendations:read`, `.config:read` and `.plugin:access`. Those are for what the datasource cannot answer:

- the policy INVENTORY, including policies configured but inactive in the window - the datasource only names policies that fired;
- recommendations not yet applied, which is the pending-work queue rather than the achieved saving;
- whether Adaptive Traces is configured at all on a stack that is not currently dropping anything.

**The plugin defines exactly one role, `admin`, bundling `config:write`, `policies:write`, `policies:delete` and `recommendations:apply` with the reads.** That role must never be assigned. The four read actions are cherry-picked into this project own custom role, and the mutations stay in REFUSED_ACTIONS.

Expect the plugin route to be awkward. Adaptive Logs is reached through `/api/plugin-proxy/<id>/...` and NOT `/api/plugins/<id>/resources/...`; the resource proxy was observed returning 500 for every path on a lab stack including `/resources/health`. Probe health first, and treat a 500 as "the proxy is down here", never as "this route does not exist".

## Deliberately out of scope

Adaptive Profiles. The estate has one stack with any profiling data at all, so there is nothing to measure and no consumer to justify the standing authority.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [ ] #1 Enablement and reduction panels ship first, over grafanacloud-usage, with no collector change
- [ ] #2 Reduction ratio uses the enabled-stack denominator and states it
- [ ] #3 Enablement denominator is windowed to match its numerator
- [ ] #4 Discarded spans reported separately from sampled-out, never summed
- [ ] #5 Policy detail is a view column; the policy label never becomes a metric label
- [ ] #6 Policy inventory collection uses only the four read actions; the bundled admin role is never assigned
- [ ] #7 Plugin proxy health is probed before concluding a route is absent
- [ ] #8 Adaptive Profiles remains uncollected and the reason is recorded
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
1. Ship and validate a dashboard-only Adaptive Traces surface first: matched 24-hour enablement denominator, enabled-population byte reduction, separate discarded-span rate and live per-policy table. Commit and push this no-collector slice while the task remains In Progress.
2. Add the stack-reader source only after the panel commit, probing plugin health before config, policy and recommendation routes and withholding unavailable stacks rather than publishing zeros.
3. Publish identity-bearing policy/recommendation detail only as S3 views, emit only bounded aggregate metrics if a trend is justified, derive VIEW_INPUTS and update capability/privacy documentation.
4. Run the full gates and CodeRabbit for the collector slice, finalize Backlog, commit, push and continue to Phase 3.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
PANEL-FIRST CHECKPOINT. The Coverage surface now reads Adaptive Traces directly from grafanacloud-usage: a 24-hour enabled-stack count beside the identically windowed trace-ingesting denominator; time-integrated dropped bytes divided only by received bytes on the reporting population; discarded spans as a separate 24-hour average rate; and a live per-policy sampled-span table. The policy label is rendered only from the live datasource and is not copied into collector output. The panel descriptions explicitly reject an estate-wide saving interpretation and name a funded rollout to one high-volume trace-ingesting stack as the next step.

This checkpoint changes dashboard configuration only. No collector source, credential, permission, emitted metric or S3 view was added. Dashboard coverage gate: 158 passed, 2 skipped, 106 subtests.

ROUTE-DISCOVERY CHECKPOINT. Public Grafana documentation verifies the direct hosted Tempo GET routes for policies, individual policies and recommendations, plus the four read-only plugin actions already granted. It does not document the stack-local plugin-proxy path, a proxy health endpoint or the config/status route. The direct API requires a separate tenant Basic-auth access-policy token with adaptive-traces:admin in the published example, so it is not adopted under the existing least-privilege reader seam. Collector work is parked until the plugin-proxy contract is verified; the shipped datasource-only panels remain valid.

ROUTE-DISCOVERY TECHNIQUE FOUND, 2026-09-11. This task is parked on "the plugin-proxy contract is
verified". There is now a live-verified, general way to verify it for any Grafana Cloud app plugin,
found while investigating GCI-0022:

1. `GET {stackUrl}/api/plugins/<plugin-id>/settings` returns a `module` field pointing at the
   plugin's `module.js` on `plugins-cdn.grafana.net`, version-pinned.
2. Fetch that `module.js`. It is a webpack loader carrying a chunk map of `{id: "<hash>"}` pairs.
3. Fetch each chunk as `<baseUrl>/<id>.js?_cache=<hash>`.
4. Grep the chunks for `/api/plugins/`, `/api/plugin-proxy/` and `/api/datasources/proxy/`. The
   frontend's own call sites are the contract.

On `grafana-dbcfg-app` this produced three real routes in one pass, including two `resources/v1/...`
paths that answer 200 - which also corrects a belief this repository was carrying. `/api/plugins/<id>/
resources/...` returning 500 is true for `grafana-adaptivelogs-app` and FALSE as a general claim: the
route pattern is per-plugin and must be discovered, not inferred from another plugin.

Second finding relevant here: `grafana-dbcfg-app` declares NO RBAC actions of its own - verified
against a live stack's `/api/access-control/user/actions`, which lists every
`grafana-adaptive-metrics-app.*` action and nothing for dbcfg. So a plugin with no declared actions is
reached with the generic `{"action": "plugins.app:access", "scope": "plugins:id:<plugin>"}` alone.
Check whether `grafana-adaptivetraces-app` declares its own actions before assuming the granted
`.policies:read` / `.recommendations:read` / `.config:read` / `.plugin:access` set is what the resource
route actually gates on.

Third, incidental but it settles a hypothesis recorded on GCI-0014: `grafana-adaptive-metrics-app.exemptions:read`
DOES exist as a stack-level plugin action. That is consistent with exemptions being plugin-internal and
unreachable from an org-realm scope, which is why `adaptive-metrics-exemptions:read` was dropped.

Not actioned here - this task stays Parked and out of the 2026-09-11 wave 1 scope. Recorded so the
resume does not start by re-deriving the technique.
<!-- SECTION:NOTES:END -->
