# Capability and credential map

This file records which identity reaches each source. Endpoint availability still varies by plan,
region and product rollout, so a deployment must record actual HTTP status and coverage rather than
turning an unavailable source into zero.

## Org-realm reader

`collector.config.READER_SCOPES` is authoritative:

| Scope | Routes this collector calls, not the scope boundary | Basic-auth user |
|---|---|---|
| `stacks:read` | Grafana.com stack inventory | bearer |
| `stack-users:read` | per-stack users through Grafana.com | bearer |
| `stack-plugins:read` | per-stack plugins through Grafana.com | bearer |
| `org-members:read` | organisation membership | bearer |
| `accesspolicies:read` | regional access-policy inventory | bearer |
| `metrics:read` | Mimir cardinality API **and the whole Prometheus query API** | `hmInstancePromId` |
| `logs:read` | `/loki/api/v1/labels`, `/loki/api/v1/label/<name>/values`, `/config/tenant/v1/limits` | `hlInstanceId` |
| `traces:read` | `/tempo/api/v2/search/tags`, `/tempo/api/v2/search/tag/<t>/values` | `htInstanceId` |
| `profiles:read` | `querier.v1.QuerierService/LabelValues` | `hpInstanceId` |
| `rules:read` | `/api/prom/api/v1/rules`, `/api/prom/api/v1/alerts`, Loki `/prometheus/api/v1/rules` | signal instance id |
| `alerts:read` | `/alertmanager/api/v2/{status,alerts,silences}`, `/api/v1/alerts` | `amInstanceId` |
| `adaptive-metrics-rules:read` | `/aggregations/rules` | `hmInstancePromId` |
| `adaptive-metrics-recommendations:read` | `/aggregations/recommendations?verbose=true` | `hmInstancePromId` |
| `adaptive-metrics-config:read` | `/aggregations/recommendations/config` | `hmInstancePromId` |
| `adaptive-metrics-rules:read` (segments) | `/aggregations/rules/segments`, `/aggregations/rules?segment=<id>` | `hmInstancePromId` |
| `adaptive-metrics-recommendations:read` (segments) | `/aggregations/recommendations?segment=<id>` | `hmInstancePromId` |
| `fleet-management:read` | Fleet Management Connect-RPC list methods | stack `id` |

The route column is an implementation inventory. It is not a claim that the credential cannot call
other read routes.

- **`logs:read` is a full Loki read scope.** A scope-isolated probe returned log content from
  `/loki/api/v1/query_range`, and the same scope reaches the effective tenant limits route. It stays
  because the label inventory needs it, no narrower Grafana Cloud scope reaches label names and
  values, and planned log analytics will need log reads outright. The collector does not call a log
  query endpoint: its Loki reads are fixed label and effective-limit routes. That restraint is an
  implementation property enforced by source review, not a credential boundary.
- **`traces:read` breadth beyond the two tag routes is unverified.** The isolating probe is a
  throwaway org-realm policy carrying only `traces:read`, followed by a Tempo search and trace fetch
  over synthetic data, then deletion and a residual-policy check.
- **`profiles:read` breadth beyond `LabelValues` is unverified.** The isolating probe is a throwaway
  org-realm policy carrying only `profiles:read`, followed by a Pyroscope profile query over synthetic
  data, then deletion and a residual-policy check.
- **`rules:read` reaches rule definitions and firing alert payloads.** The latter include full customer
  label sets. The collector reduces those payloads to bounded counts and never republishes the labels.

One org-realm token reaches all four signal databases in every region of the estate. The region hint in
the token payload does not constrain the data plane. The basic-auth user differs per signal and comes
from `dataplane.AUTH_FIELD`; Fleet Management and the Alertmanager are the two that do not use a signal
instance id.

The Fleet calls use POST because that is the RPC transport; the scope and methods remain reads.
Grafana.com is paced at six requests per second. Paused stacks are skipped when the control plane
answers with its paused-stack conflict response.

There is no `stack-service-accounts:read` org scope. Only the write scope exists, so it is not
given to the collector. Service-account inventory is reachable through each stack's local reader.

`adaptive-metrics-exemptions:read` is deliberately absent from `READER_SCOPES`. The initial sweep
covered 34 candidate paths plus deliberate nonexistent controls; later checks expanded the set past
forty across two independent stacks. Every candidate returned the same plain-text 404 as the controls,
and the result remained unchanged on a stack with applied rules, auto apply enabled and a configured
segment. That rules out a route which appears only after data exists.

The org-realm scope was the wrong mechanism. Exemptions are a stack-level plugin RBAC resource. The
Grafana plugin proxy could not settle a concrete read route on the tested stack because every
`resources/*` path returned `500 plugin.requestFailureError`, including controls. A future route probe
must first call the plugin health resource with a stack reader; a 500 means the proxy is unavailable
and proves nothing about the candidate route.

A scope existing is not evidence a route does. Grafana mints scope families per resource type, so an
unexposed or plugin-internal resource still gets a public scope name.

**Resolved: exemptions are a STACK-LEVEL PLUGIN RBAC resource, not an org access-policy scope.** The
org scope name was the wrong mechanism, which is why no route answers it. A live stack exposes these
Adaptive Metrics plugin roles, and their underlying actions are what actually gate the data:

| Plugin role | Actions |
|---|---|
| `plugins:grafana-adaptive-metrics-app:exemptions-reader` | `grafana-adaptive-metrics-app.exemptions:read`, `.plugin:access` |
| `plugins:grafana-adaptive-metrics-app:rules-reader` | `.rules:read`, `.recommendations:read`, `.plugin:access` |
| `plugins:grafana-adaptive-metrics-app:segments-reader` | `.segments:read`, `.config:read`, `.plugin:access` |
| `plugins:grafana-adaptive-metrics-app:config-reader` | `.config:read`, `.plugin:access` |
| `plugins:grafana-adaptive-metrics-app:plugin-access` | `.plugin:access`, `plugins.app:access` scoped `plugins:id:grafana-adaptive-metrics-app` |

Enumerate them on any stack with
`GET /api/access-control/roles?includeHidden=true`, filtering names prefixed `plugins:`.

So reading exemptions means adding `grafana-adaptive-metrics-app.exemptions:read` and the
`plugins.app:access` pair to the per-stack reader's custom role - the same shape the project already
uses for Adaptive Logs - not widening the org credential. The rules, recommendations, segments and
config data all remain reachable on the Mimir host with the org token and need no plugin role.

**Segments are a real and previously unrecorded surface.** A segment scopes a rule set to a selector,
so a stack with segments has rules that are not estate-wide and its savings arithmetic must be read
per segment rather than globally. Both segment routes above were verified 200 with a live segment
present.

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
- retention change requests through the Databases Configuration app resource route;
- service-account inventory and permission metadata;
- datasource metadata and caching state;
- folders, dashboards, public dashboards and snapshots;
- teams, team permissions, team roles, user roles and custom-role metadata;
- alert-rule and receiver inventory without receiver secrets;
- the datasource proxy for exactly `grafanacloud-usage-insights` on every stack;
- the datasource proxy for exactly `grafanacloud-usage` on the nominated write stack only.

`datasources:read` uses `datasources:*` because it lists metadata.
`datasources:query` is separately uid-pinned. Ordinary readers receive only
`datasources:uid:grafanacloud-usage-insights`; the write-stack reader additionally receives
`datasources:uid:grafanacloud-usage` for the bounded capability-adoption input. No reader can query
arbitrary production datasources.

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

### Loki retention

Effective tenant limits come from `/config/tenant/v1/limits` on the Loki dataplane under the existing
org CAP and `logs:read`. The path has no `/loki` prefix. The deprecated
`/loki/api/v1/config/limits/applied` route needs a different scope and is not used. Self-serve change
requests come from the stack-local Databases Configuration app resource route; they are evidence that
a request happened, never evidence that no direct override exists.

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
