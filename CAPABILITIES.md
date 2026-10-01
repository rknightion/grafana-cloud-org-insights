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
| `profiles:read` | native `querier.v1.QuerierService/LabelNames` and `LabelValues` | `hpInstanceId` |
| `rules:read` | declared but no current source call; verified rule/alert routes discussed below | signal instance id |
| `alerts:read` | declared but no current source call; verified Alertmanager routes discussed below | `amInstanceId` |
| `adaptive-metrics-rules:read` | `/aggregations/rules` | `hmInstancePromId` |
| `adaptive-metrics-recommendations:read` | `/aggregations/recommendations?verbose=true` | `hmInstancePromId` |
| `adaptive-metrics-config:read` | `/aggregations/recommendations/config` | `hmInstancePromId` |
| `fleet-management:read` | Fleet Management Connect-RPC list methods | stack `id` |

The route column is an implementation inventory. It is not a claim that the credential cannot call
other read routes.

- **`logs:read` is a full Loki read scope.** A scope-isolated probe returned log content from
  `/loki/api/v1/query_range`, and the same scope reaches the effective tenant limits route. It stays
  because the label inventory needs it, no narrower Grafana Cloud scope reaches label names and
  values, and planned log analytics will need log reads outright. The collector does not call a log
  query endpoint: its Loki reads are fixed label and effective-limit routes. That restraint is an
  implementation property enforced by source review, not a credential boundary.
- **`traces:read` permits trace content reads, not just tag inventory.** An isolated stack-realm
  policy carrying only this scope returned Tempo search results and a nonempty fetched trace. See
  the route-level observations and realm limits below; the collector still calls only tag routes.
- **`profiles:read` permits profile content reads, not just label inventory.** An isolated
  stack-realm policy carrying only this scope returned profile types and a populated merged
  flamegraph. See the observations below; the collector calls only `LabelNames` and `LabelValues`.
- **`rules:read` reaches rule definitions and firing alert payloads.** The latter include full customer
  label sets. These routes are not currently called; any future reader must reduce payloads to
  bounded counts and never republish the labels.

One org-realm token reaches all four signal databases in every region of the estate. The region hint in
the token payload does not constrain the data plane. The basic-auth user differs per signal and comes
from `dataplane.AUTH_FIELD`; Fleet Management and the Alertmanager are the two that do not use a signal
instance id.

The Fleet calls use POST because that is the RPC transport; the scope and methods remain reads.
The label-risk source has an exact two-path native Pyroscope read-POST exception. The observed-name
source's older `dataplane._connect_rpc` helper also reads Pyroscope LabelValues; its legacy substring
path guard is not an exact allow-list and is not authority for additional RPC methods. The shared
HTTP client stays GET-only. All these source transports fence caller waits with `collector.netbound`,
not hard cancellation of surviving reads; see [resource fences](docs/source-resource-fences.md).
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

**Segments are an uncollected surface.** `/aggregations/rules/segments`,
`/aggregations/rules?segment=<id>` and `/aggregations/recommendations?segment=<id>` were verified
200 with a live segment present, but `dataplane.adaptive_metrics` does not enumerate or select
segments. A segment scopes a rule set to a selector; the collector's unsegmented aggregate must not
be claimed as a verified segment-aware estate saving.

### Scope-isolated trace and profile content reads

On 2026-09-30, a control-organisation probe used one live-inventory stack and two temporary access
policies. Each policy had exactly one scope (`traces:read` or `profiles:read`), exactly one **stack
realm**, and no label policies. Signal-specific basic-auth users came from that stack's inventory.
No raw trace IDs, span content, profile names or flamegraph content are reproduced here.

| Isolated scope | Method and route | Observed result |
|---|---|---|
| `traces:read` | GET `/tempo/api/search` with a 24-hour window | HTTP 200 with returned trace IDs |
| `traces:read` | GET `/tempo/api/traces/<returned-ID>` | HTTP 200 with nonempty trace batches |
| `profiles:read` | POST `/querier.v1.QuerierService/ProfileTypes` with the same 24-hour window | HTTP 200 with nonempty profile types |
| `profiles:read` | POST `/querier.v1.QuerierService/SelectMergeStacktraces` with a returned `profileTypeID` and `labelSelector={}` | HTTP 200 with populated flamegraph names and levels, and a positive total |

The Pyroscope POSTs are read-only RPC methods, not profile ingestion or mutation. These are probe
observations, not new collector calls; the collector's HTTP client and declared scopes are unchanged.
Both temporary policies were deleted by their recorded object IDs (HTTP 204), then re-read by those
same IDs (HTTP 404). No preexisting policy was modified or deleted.

**Realm applicability and remaining ambiguity:** the positive content reads above were isolated in
stack-realm policies, not org-realm policies. The collector grants the same scope names in an org
realm, so its tag/label-only implementation must not be described as a credential-enforced content
boundary. However, this probe did not establish these content routes with a single-scope org-realm
token, across other stacks or regions, or under label policies. It tested no denied-route controls
and establishes no exhaustive scope boundary. Availability and content coverage outside the tested
stack remain unverified; a missing result must not be interpreted as permission denial or zero data.

Reference contracts: [Grafana Cloud access policies and tokens](https://grafana.com/docs/grafana/latest/developer-resources/api-reference/cloud-api/#access-policies-and-tokens)
and [Pyroscope HTTP API](https://grafana.com/docs/pyroscope/latest/reference-server-api/).
The observations above are from the scope-isolated live probe, not inferred from those documents.

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
- count-only Adaptive Traces config availability, policies and recommendations through
  `/api/plugin-proxy/grafana-adaptivetraces-app/{config,policies,recommendations}`;
  the preliminary `health` GET is status-only and does not gate these domains;
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

An optional, default-off `GCINSIGHT_READER_PRODUCT_READS` setting accepts `slo` and
`synthetic-monitoring`. When selected, `slo` adds unscoped
`grafana-slo-app.orgpreferences:read` and `grafana-slo-app.slo:read`, plus `plugins.app:access` scoped
to `plugins:id:grafana-slo-app`. `synthetic-monitoring` adds unscoped
`grafana-synthetic-monitoring-app:read` and `grafana-synthetic-monitoring-app.checks:read`, plus
`plugins.app:access` scoped to `plugins:id:grafana-synthetic-monitoring-app`. These pairs were checked
against live role metadata on 2026-09-23. Unsetting the option removes those product pairs during
reconciliation without replacing a working reader token. A deployment must explicitly approve and
select a family; generic defaults grant neither. T2 gathers count-only SLO definitions when `slo` is
selected, but the Synthetic Monitoring app grant does not establish a reachable check-list route.

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

Query-mix detail uses the same token, datasource uid, exact `instance_id` guard and 24-hour window.
No extra permission is required. The datasource-type dimension is inference about a backend, not an
application identity. Two active dev stacks returned nonzero request counts but no non-empty
`panelPluginId` on 2026-09-23, so the panel-plugin half has no live positive proof.

### Adaptive Metrics

The direct `/aggregations/recommendations?verbose=true` response is required for series counts.
The default response is structurally complete-looking but insufficient for savings arithmetic.

### Adaptive Logs

The working read route is the Adaptive Logs plugin proxy. Frontend app resource paths can return 500
and datasource-proxy calls can report authentication failure even when the reader role is correct.
Recommendation volume has no declared or settable time window.

### SLO and Adaptive Traces

T2's optional SLO list GET is `/api/plugins/grafana-slo-app/resources/v1/slo`. It projects definition
counts, configured-alerting counts and closed provenance/status/source enums, not SLI time series
or firing alerts. Adaptive Traces projects config availability, closed policy-type counts and pending
recommendation counts through the routes above with the existing reader; this is operational
sufficiency of the full role, not proof of isolated minimum permissions. Config availability does not
prove enablement, and recommendation counts do not measure achieved saving. Both readers discard
raw objects and use the [guarded transport/schema fences](docs/source-resource-fences.md).

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

- The SLO app's documented `GET /api/plugins/grafana-slo-app/resources/v1/slo` returned HTTP 403
 with the existing stack reader on three development and six customer-estate stacks in a read-only
 sample. The declared reader lacks `grafana-slo-app.slo:read` and plugin access scoped to
 `plugins:id:grafana-slo-app`. A live development role-definition GET also listed
 `grafana-slo-app.orgpreferences:read` in the SLO reader role. The optional dev-only grant above
 addresses that permission seam; this earlier 403 does not say whether those stacks have SLOs.
- A live role-definition GET on one development stack showed the Synthetic Monitoring checks reader
 would grant `grafana-synthetic-monitoring-app:read`,
 `grafana-synthetic-monitoring-app.checks:read` and plugin access on that app. The IRM integrations
 reader would grant `grafana-irm-app.integrations:read` and its plugin access. The k6 reader would
 grant `k6-app.settings:read` and plugin access on `k6-app`; that role name alone does not prove a
 k6 runs API is reachable. SLO and Synthetic pairs are optional and default off; k6 and IRM remain
 undeclared. Product object and run routes were not queried with an expanded identity at that time.
- In the same sample, `/api/plugins`, `/api/datasources`, `/api/v1/provisioning/alert-rules`,
 `/api/search/` and the existing Adaptive Logs plugin-proxy recommendation route returned HTTP 200.
 The plugin, datasource, rule and search lists were populated; a 200 alone is not an unfiltered
 inventory guarantee. Assistant `/api/v1/usage/hero-stats` was called without the endpoint's required
 parameters and returned HTTP 400 on all nine; this is a rejected request shape, not a role verdict.
- Synthetic Monitoring result inventory has no verified safe unattended read route.
- The Synthetic Monitoring app source calls `GET <synthetic-monitoring-datasource URL>/sm/check/list`
 to list checks. The datasource plugin maps that to its backend API through Grafana's datasource
 proxy. A guarded dev reader GET to `/api/datasources/proxy/uid/<synthetic datasource uid>/sm/check/list`
 returned 403 before the optional product grant on 2026-09-23. The reader's datasource query scope
 intentionally excludes this datasource, so the optional app read pairs alone do not establish a
 reachable check-list route. The backend's separate REST API requires a Synthetic Monitoring token.
 Do not add a datasource query grant or mint that token without a separate explicit deployment
 decision. See the
 [plugin source](https://github.com/grafana/synthetic-monitoring-app/blob/97fefc26fac1abd508f753ec41807a448e957ae5/src/datasource/DataSource.ts)
 and [Grafana API documentation](https://grafana.com/docs/grafana-cloud/observe-and-act/testing/synthetic-monitoring/api-reference/).
- Adaptive Profiles endpoints have not produced a verified read contract.
- Adaptive Traces detail and mutation are not collected. The count-only GET consumer described above
  uses the existing reader without adding the plugin's bundled admin role.
- Regional usage-insights datasources on one central stack are not a substitute for per-stack readers.
- Grafana.com dashboard lists are incomplete or empty; stack-local APIs own that inventory.

## Write identities

The runtime writer carries only `metrics:write` and `logs:write` in the nominated write
stack's realm. The provisioner carries `stacks:read` and
`stack-service-accounts:write` but is a separate scheduled task and secret key. Build-time Grafana
credentials are supplied only to dashboard/alert publication tools and should be short-lived.

## Bounded label-risk reads

The daily label-risk source uses the existing `metrics:read`, `logs:read`, `traces:read` and
`profiles:read` scopes with inventory per-signal tenant IDs. No scope, role or credential is
changed. GET label routes are Mimir `/api/prom/api/v1/labels` and `/api/prom/api/v1/label/<key>/values`,
Loki `/loki/api/v1/labels` and `/loki/api/v1/label/<key>/values`, and Tempo
`/tempo/api/v2/search/tags` and `/tempo/api/v2/search/tag/<scoped-key>/values`. Pyroscope exclusively
uses the two read-only native POST paths `/querier.v1.QuerierService/LabelNames` and
`/querier.v1.QuerierService/LabelValues`
on inventory `hpInstanceUrl`, authenticated as `hpInstanceId`. Responses use `names` for both
operations. This is not authority for another QuerierService method or a write.

These four source shapes were mapped in staff discovery; directly isolated label-path scope
sufficiency and customer-estate precision/recall are not proven by the offline contract suite.
Raw matches have only the approved S3 view/private hydration audience, never Loki or metrics.
