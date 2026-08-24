# Credentials and permissions

Four identities, each with the smallest scope that does its job. This page records which identity reaches each source.

Endpoint availability varies by plan, region and product rollout, so a deployment records the actual HTTP status and coverage rather than turning an unavailable source into a zero.

## The org-realm reader

`collector.config.READER_SCOPES` is authoritative. One org-realm token reaches all four signal databases in every region of the estate - the region hint in the token payload does not constrain the data plane.

| Scope | Reaches | Basic-auth user |
|---|---|---|
| `stacks:read` | Grafana.com stack inventory | bearer |
| `stack-users:read` | per-stack users through Grafana.com | bearer |
| `stack-plugins:read` | per-stack plugins through Grafana.com | bearer |
| `org-members:read` | organisation membership | bearer |
| `accesspolicies:read` | regional access-policy inventory | bearer |
| `metrics:read` | Mimir cardinality API **and the whole Prometheus query API** | `hmInstancePromId` |
| `logs:read` | Loki label and label-value endpoints | `hlInstanceId` |
| `traces:read` | Tempo search-tag endpoints | `htInstanceId` |
| `profiles:read` | Pyroscope `LabelValues` | `hpInstanceId` |
| `rules:read` | Prometheus and Loki ruler inventory | signal instance id |
| `alerts:read` | Alertmanager status, alerts and silences | `amInstanceId` |
| `adaptive-metrics-rules:read` | `/aggregations/rules` | `hmInstancePromId` |
| `adaptive-metrics-recommendations:read` | `/aggregations/recommendations?verbose=true` | `hmInstancePromId` |
| `adaptive-metrics-config:read` | `/aggregations/recommendations/config` | `hmInstancePromId` |
| `fleet-management:read` | Fleet Management Connect-RPC list methods | stack `id` |

The basic-auth user differs per signal and comes from `dataplane.AUTH_FIELD`. Fleet Management and the Alertmanager are the two that do not use a signal instance id.

Fleet calls use POST because that is the RPC transport. The scope and the methods remain reads, and they live outside the collector's HTTP client - which rejects every method except GET.

Grafana.com is paced at six requests per second. Paused stacks are skipped when the control plane answers with its paused-stack conflict response.

Two things the org token deliberately does not have:

- **`adaptive-metrics-exemptions:read`** is declared to match the deployed policy, but no path has answered 200. Eight candidates under `/aggregations` were tried and all 404. Treat it as reserved, not as a capability, until a route is verified.
- **`stack-service-accounts:read` does not exist.** Only the write scope does, so it is not given to the collector. Service-account inventory is reached through each stack's local reader instead.

### The two scopes that reach beyond inventory

`alerts:read` and `rules:read` are not free, and the collector must not treat them as such.

- **`/alertmanager/api/v2/status` returns the stack's raw Alertmanager configuration** in `config.original`, `http_config` included. Where a stack's contact points live in Alertmanager rather than in Grafana, that YAML can carry webhook URLs and tokens. Nothing derived from that body may be stored, logged or emitted beyond bounded counts.
- **`/api/prom/api/v1/alerts` returns firing instances with their full customer label sets.** Unbounded and identity-bearing. Count them; never carry them into a metric label.
- The Loki ruler answers **404 with `no rule groups found`** when a stack has no rules. That is an empty inventory, not a permission failure. `/prometheus/api/v1/rules` on the same host returns 200 with an empty group list for the same stack, so prefer it and read the 404 as zero.

## The stack-local reader

The provisioner declares `collector.provision.DESIRED_PERMISSIONS`. It creates a basic-role-`None` service account on each stack and assigns `custom:gcinsight.reader`. Drift is compared as action/scope pairs, not action names.

The role can read:

- Assistant aggregate usage, tenant-scoped inventory and investigations counts;
- Adaptive Logs recommendations through the plugin-proxy route;
- service-account inventory and permission metadata;
- datasource metadata and caching state;
- folders, dashboards, public dashboards and snapshots;
- teams, team permissions, team roles, user roles and custom-role metadata;
- alert-rule and receiver inventory, without receiver secrets;
- the datasource proxy for exactly `grafanacloud-usage-insights`.

`datasources:read` uses `datasources:*` because it lists metadata. `datasources:query` is separately pinned to `datasources:uid:grafanacloud-usage-insights` and is never widened to `datasources:*`. The reader cannot query arbitrary production datasources.

The declaration explicitly refuses decrypted alert secrets, secure values, user session tokens, Grafana auth settings, support bundles, provisioning writes and Adaptive Traces mutation actions. `chats:access` is not granted.

**Several list endpoints return HTTP 200 with a permission-filtered empty list.** Coverage is therefore part of the result, and a zero is trusted only after the matching role pair is confirmed present.

## Write identities

The runtime writer carries only `metrics:write` and `logs:write`, in the nominated write stack's realm. It cannot touch any other stack because the realm forbids it, not because a scope check says so.

The provisioner carries `stacks:read` and `stack-service-accounts:write`, and is a separate scheduled task with a separate secret key.

Build-time Grafana credentials are supplied only to the dashboard and alert publication tools, and should be short-lived.

## Source-specific contracts

### Usage insights

Each stack's usage-insights datasource exposes a **regional** tenant, so every query made with that stack's own reader includes `instance_type="grafana"` and `instance_id="<stack id>"`.

The label is the stack `id` for Grafana events, not its Prometheus tenant id. The query helper refuses a selector without `instance_id`. Get it wrong and one stack's figures are repeated across every stack in its region, with nothing failing.

### Adaptive Metrics

`?verbose=true` is required for series counts. The default response is structurally complete-looking and insufficient for savings arithmetic.

### Adaptive Logs

The working read route is the Adaptive Logs plugin proxy. Frontend app resource paths can return 500, and datasource-proxy calls can report authentication failure even when the reader role is correct. Recommendation volume has no declared or settable time window.

### Assistant

The working route is the Assistant app's plugin-resource proxy, and usage endpoints take epoch milliseconds. Tenant-scoped objects are readable. User-scoped objects are invisible to every other identity and cannot be counted as estate inventory - that is a product boundary, not a reason to widen the role.

### Public dashboards

Enumeration and usage events are separate. The stack API enumerates configured shares including ones nobody opens; usage-insights events identify public shares observed in use. `accessToken` is the live public URL and is never stored, logged or emitted.

### Alert routing

The reader collects rule and receiver names, not decrypted receiver configuration. A rule with no direct receiver inherits the stack notification policy; that is reported as routing exposure, not automatically labelled broken.

## Known unavailable or rejected routes

- Synthetic Monitoring result inventory has no verified safe unattended read route.
- Adaptive Profiles endpoints have not produced a verified read contract.
- Adaptive Traces collection is absent until a concrete read-only consumer and permission contract exist.
- Regional usage-insights datasources on one central stack are not a substitute for per-stack readers.
- Grafana.com dashboard lists are incomplete or empty; stack-local APIs own that inventory.
