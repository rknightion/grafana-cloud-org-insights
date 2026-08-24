# Capability and credential map

This file records which identity reaches each source. Endpoint availability still varies by plan,
region and product rollout, so a deployment must record actual HTTP status and coverage rather than
turning an unavailable source into zero.

## Org-realm reader

`collector.config.READER_SCOPES` is authoritative:

| Scope | Verified route | Basic-auth user |
|---|---|---|
| `stacks:read` | Grafana.com stack inventory | bearer |
| `stack-users:read` | per-stack users through Grafana.com | bearer |
| `stack-plugins:read` | per-stack plugins through Grafana.com | bearer |
| `org-members:read` | organisation membership | bearer |
| `accesspolicies:read` | regional access-policy inventory | bearer |
| `metrics:read` | Mimir cardinality API **and the whole Prometheus query API** | `hmInstancePromId` |
| `logs:read` | `/loki/api/v1/labels`, `/loki/api/v1/label/<name>/values` | `hlInstanceId` |
| `traces:read` | `/tempo/api/v2/search/tags`, `/tempo/api/v2/search/tag/<t>/values` | `htInstanceId` |
| `profiles:read` | `querier.v1.QuerierService/LabelValues` | `hpInstanceId` |
| `rules:read` | `/api/prom/api/v1/rules`, `/api/prom/api/v1/alerts`, Loki `/prometheus/api/v1/rules` | signal instance id |
| `alerts:read` | `/alertmanager/api/v2/{status,alerts,silences}`, `/api/v1/alerts` | `amInstanceId` |
| `adaptive-metrics-rules:read` | `/aggregations/rules` | `hmInstancePromId` |
| `adaptive-metrics-recommendations:read` | `/aggregations/recommendations?verbose=true` | `hmInstancePromId` |
| `adaptive-metrics-config:read` | `/aggregations/recommendations/config` | `hmInstancePromId` |
| `adaptive-metrics-exemptions:read` | **none found** | - |
| `fleet-management:read` | Fleet Management Connect-RPC list methods | stack `id` |

One org-realm token reaches all four signal databases in every region of the estate. The region hint in
the token payload does not constrain the data plane. The basic-auth user differs per signal and comes
from `dataplane.AUTH_FIELD`; Fleet Management and the Alertmanager are the two that do not use a signal
instance id.

The Fleet calls use POST because that is the RPC transport; the scope and methods remain reads.
Grafana.com is paced at six requests per second. Paused stacks are skipped when the control plane
answers with its paused-stack conflict response.

There is no `stack-service-accounts:read` org scope. Only the write scope exists, so it is not
given to the collector. Service-account inventory is reachable through each stack's local reader.

`adaptive-metrics-exemptions:read` is declared to match the deployed policy, but no path has answered
200. Eight candidates under `/aggregations` were tried and all 404. Treat the scope as reserved, not as
a capability, until a route is verified.

### The two scopes that reach beyond inventory

`alerts:read` and `rules:read` are not free, and the collector must not treat them as such.

- **`/alertmanager/api/v2/status` returns the stack's RAW Alertmanager configuration** in
  `config.original`, `http_config` included. Where a stack's contact points live in Alertmanager rather
  than in Grafana, that YAML can carry webhook URLs and tokens. Nothing derived from that body may be
  stored, logged or emitted beyond bounded counts. Treat it exactly like `accessToken` on a public
  dashboard.
- **`/api/prom/api/v1/alerts` returns firing instances with their full customer label sets.** Unbounded
  and identity-bearing. Count them; never carry them into a metric label.
- The Loki ruler answers **404 with `no rule groups found`** on `/loki/api/v1/rules` when a stack has no
  rules. That is an empty inventory, not a permission failure. `/prometheus/api/v1/rules` on the same
  host returns 200 with an empty group list for the same stack, so prefer it and read the 404 as zero.

## Stack-local reader

The provisioner declares `collector.provision.DESIRED_PERMISSIONS`. It creates a basic-role-None
service account and assigns `custom:gcinsight.reader`. Drift is compared as action/scope pairs,
not action names.

The role can read:

- Assistant aggregate usage, tenant-scoped inventory and investigations counts;
- Adaptive Logs recommendations through the plugin-proxy route;
- service-account inventory and permission metadata;
- datasource metadata and caching state;
- folders, dashboards, public dashboards and snapshots;
- teams, team permissions, team roles, user roles and custom-role metadata;
- alert-rule and receiver inventory without receiver secrets;
- the datasource proxy for exactly `grafanacloud-usage-insights`.

`datasources:read` uses `datasources:*` because it lists metadata.
`datasources:query` is separately pinned to
`datasources:uid:grafanacloud-usage-insights`. The reader cannot query arbitrary production
datasources.

The declaration explicitly refuses decrypted alert secrets, secure values, user session tokens,
Grafana auth settings, support bundles, provisioning writes and Adaptive Traces mutation actions.
`chats:access` is not granted.

Several list endpoints return HTTP 200 with a permission-filtered empty list. Coverage is therefore
part of the result, and a zero is trusted only after the matching role pair is present.

## Source-specific contracts

### Usage insights

Each stack's usage-insights datasource exposes a regional tenant. Every query is made with that stack's
own reader and includes:

- `instance_type="grafana"`;
- `instance_id="<stack id>"`.

The label is the stack `id` for Grafana events, not its Prometheus tenant id. The query helper
refuses a selector without `instance_id`. Other usage-insights instance types are not queried by
Pillar J.

### Adaptive Metrics

The direct `/aggregations/recommendations?verbose=true` response is required for series counts.
The default response is structurally complete-looking but insufficient for savings arithmetic.

### Adaptive Logs

The working read route is the Adaptive Logs plugin proxy. Frontend app resource paths can return 500
and datasource-proxy calls can report authentication failure even when the reader role is correct.
Recommendation volume has no declared or settable time window.

### Assistant

The working route is the Assistant app's plugin-resource proxy. Usage endpoints take epoch
milliseconds. Tenant-scoped objects are readable; user-scoped objects are invisible to every other
identity and cannot be counted as estate inventory. Watcher and investigation inventory boundaries are
product boundaries, not reasons to widen the role.

### Public dashboards

Enumeration and usage events are separate:

- the stack API enumerates configured shares, including ones nobody opens;
- usage-insights events identify public shares observed in use.

`accessToken` is the live public URL and is never stored, logged or emitted.

### Alert routing

The reader collects rule and receiver names but not decrypted receiver configuration. A rule with no
direct receiver inherits the stack notification policy; this is reported as routing exposure, not
automatically labelled broken.

## Known unavailable or rejected routes

- Synthetic Monitoring result inventory has no verified safe unattended read route.
- Adaptive Profiles endpoints have not produced a verified read contract.
- Adaptive Traces collection is absent until a concrete read-only consumer and permission contract
  exist.
- Regional usage-insights datasources on one central stack are not a substitute for per-stack readers.
- Grafana.com dashboard lists are incomplete or empty; stack-local APIs own that inventory.

## Write identities

The runtime writer carries only `metrics:write` and `logs:write` in the nominated write
stack's realm. The provisioner carries `stacks:read` and
`stack-service-accounts:write` but is a separate scheduled task and secret key. Build-time Grafana
credentials are supplied only to dashboard/alert publication tools and should be short-lived.
