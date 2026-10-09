# Capability and credential map

This file records which identity reaches each source. Endpoint availability still varies by plan,
region and product rollout, so a deployment must record actual HTTP status and coverage rather than
turning an unavailable source into zero.

Version boundary: stable v0.5.0 includes Synthetic counts and coverage-qualified Adaptive totals.
The additional product counters and conservative segment handling below describe current main;
they are not a claim that stable v0.5.0 or any deployment contains those later changes. Live v0.5.0
dev acceptance remains unproven. No new customer product-read grant follows this document.

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
| `rules:read` | default-off D-RULE20: Mimir `/api/prom/api/v1/rules`, `/api/prom/api/v1/alerts`; Loki `/prometheus/api/v1/rules`, count-only | signal instance id |
| `alerts:read` | default-off D-RULE20: `/alertmanager/api/v2/alerts`, `/alertmanager/api/v2/silences`, count-only; no status/config | `amInstanceId` |
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
The `dataplane._connect_rpc` helper permits only parsed paths ending in exactly
`/collector.v1.CollectorService/ListCollectors`, `/pipeline.v1.PipelineService/ListPipelines`, or
`/querier.v1.QuerierService/LabelValues`, with no query, fragment or percent-encoded path. It
requires HTTPS and a nonempty host without userinfo, using inventory-derived hosts rather than a
static host list. Its helper-local transport refuses redirects without a second request or forwarding
credentials, preserving the redirect status as `{"_http": code}`. This three-route allowlist is distinct from the label-risk source's own two-path native Pyroscope
read-POST exception for LabelNames and LabelValues. The shared HTTP client stays GET-only. All these source transports fence caller waits with `collector.netbound`,
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

**Current main discovers segmentation but does not add segment savings.** The existing reader
reaches `/aggregations/rules/segments`. Discovery distinguishes unsegmented, segmented and unknown,
including legacy inputs without a state. Whole-stack cost/value/maturity confidence requires a
known unsegmented stack; segmented or unknown stacks cannot qualify a default-only figure as an
estate saving. Qualified unsegmented subtotals remain available. Positive per-segment recommendation
counts are not proof of disjointness, fallback additivity or an achievable combined saving. The
collector creates or deletes no segments and adds no scope for this handling.

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

### D-VOL20 / D-RULE20 exact-route implementation boundary

Both readers are default-off T2 inputs, with no new scope, credential or customer
consent. D-VOL20 uses only GET `/loki/api/v1/index/volume` on fresh inventory's Loki
endpoint/tenant, selecting `service_name`, limit 100, 86400 seconds. Service values
are retained only in private hydration and S3 `loki_volume_top_services`, never
metrics, events, diagnostics, stdout or errors. Complete describes a valid bounded
response, not exhaustive coverage: measured total and remainder are unknown/null;
query-work stats and top100 sums are not whole-stack ingest totals.

D-RULE20 uses only the exact GET routes in the scope table above, authenticating
Alertmanager with live `amInstanceUrl` / `amInstanceId`. Counts cover configured
rule objects and current alert/silence states, not delivery or execution history.
Expressions, labels, annotations, names, receivers and matchers never persist.
Independent unreadable routes remain null without erasing known peer counts.
Exact 200 is required; `/alertmanager/api/v2/status` and configuration reads are
outside the collector grant, despite the broader credential reach described below.
Both inputs use the shared 10% failure ceiling, not the D-LBL12 exception. Neither
emits product metrics; each adds eight planned existing provenance series.

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

The default-off `GCINSIGHT_READER_PRODUCT_READS` setting accepts `slo`, `synthetic-monitoring`,
`synthetic-monitoring-query`, `irm-integrations`, `faro-apps`, `ml-jobs`, `cloud-accounts`,
`pdc-networks` and `reports` on current main. Later counters are not included in stable v0.5.0. When selected, `slo` adds unscoped
`grafana-slo-app.orgpreferences:read` and `grafana-slo-app.slo:read`, plus `plugins.app:access` scoped
to `plugins:id:grafana-slo-app`. `synthetic-monitoring` adds unscoped
`grafana-synthetic-monitoring-app:read` and `grafana-synthetic-monitoring-app.checks:read`, plus
`plugins.app:access` scoped to `plugins:id:grafana-synthetic-monitoring-app`. These pairs were checked
against live role metadata on 2026-09-23. Unsetting the option removes those product pairs during
reconciliation without replacing a working reader token. A deployment must explicitly approve and
select a family; generic defaults grant neither. T2 gathers count-only SLO definitions when `slo` is
selected. The original Synthetic app grant alone does not establish datasource-query access.
The separate `synthetic-monitoring-query` token requires `synthetic-monitoring`, adds query access
only to the single valid live-discovered Synthetic datasource UID and adds probes-read with empty
scope. Ambiguous or invalid discovery adds no query grant. No wildcard or other datasource query is
allowed. Without the new token, scans make no Synthetic calls; reconciliation discovers only when
needed to remove an already-held exact Synthetic query pair, never for legacy-correct readers.

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

### Optional count-only product inputs

Library panels require exact HTTP 200 on both the same-token effective permissions witness and
collection pages. Both wildcard pairs must be effective before collection starts; filtered visibility
is unavailable, never a smaller inventory. Bounded stable paging validates page numbers, totals and
unique element IDs; a duplicate, truncated or changing collection discards the entire count. An empty
complete collection measures zero, but empty live inventory is unknown and withholds the view. Models,
targets, creators, names, UIDs and IDs are transient source data, absent from the minimized scan input,
view, diagnostics and error text. Counts do not measure usage or rendered panel instances. The staff
Admin/None positive control including a non-General folder proves the witnessed pair/route, not
universal visibility. Research and default-off shipping confer no customer enablement grant.

All are default-off T2 inputs, inventory-led joins and point-in-time views, not product time-series
metrics. Each new input adds only the existing bounded input-freshness series. Unknown or unreadable
stacks are absent, never a manufactured zero; withheld views leave last-good S3 objects intact.
Readable older optional views remain eligible for dashboards. Only genuine missing objects omit an
optional table; permission, transport and parse errors remain explicit.

| Token | Exact added read pairs | Collector GET and retained output |
|---|---|---|
| `irm-integrations` | `grafana-irm-app.integrations:read` (empty), `plugins.app:access@plugins:id:grafana-irm-app` | `/api/plugins/grafana-irm-app/resources/alert_receive_channels/counters/`; integration count only |
| `faro-apps` | `grafana-kowalski-app.apps:read` (empty), `plugins.app:access@plugins:id:grafana-kowalski-app` | `/api/plugin-proxy/grafana-kowalski-app/api-proxy/api/v1/app`; count and closed web/mobile/unknown counts |
| `library-panels` | `library.panels:read@folders:*`; existing baseline `folders:read@folders:*` also required | Same-token `/api/access-control/user/permissions` coverage GET, then `/api/library-elements?kind=1&perPage=100&page=<n>`; configured library panel count only |
| `ml-jobs` | `grafana-ml-app.forecasting:read` (empty), `plugins.app:access@plugins:id:grafana-ml-app` | `/api/plugins/grafana-ml-app/resources/manage/api/v1/jobs`; configured forecast-job count |
| `cloud-accounts` | `grafana-csp-app:read` (empty), `plugins.app:access@plugins:id:grafana-csp-app` | `/api/plugin-proxy/grafana-csp-app/he-api/api/v2/stacks/<inventory id>/aws/accounts`; stack, fixed provider `aws`, count |
| `pdc-networks` | `grafana-pdc-app.private-networks:read` (empty), `plugins.app:access@plugins:id:grafana-pdc-app` | `/api/plugin-proxy/grafana-pdc-app/grafanacom-api/v1/accesspolicies`; complete-region/page count matching current stack realm and `set:pdc-signing` |
| `reports` | `reports:read@reports:*` only | `/api/reports`; configured-object count including disabled reports, not execution or delivery activity |

Transport uses fresh validated inventory origins, guarded GET without redirects, and bounded bodies
and structural traversal. Faro, ML, AWS accounts, PDC and reports require HTTP 200; valid empty
collections measure zero, partial or unsupported envelopes remain unavailable. IRM currently still
admits HTTP 206 through `response.ok`: its count-integrity acceptance is parked until an authorised
repair. Do not treat its earlier successful 200 witness as proof that this defect is fixed.

The owner accepts two named receipt risks only: IRM's same permission also reaches secret-bearing
integration configuration, but the collector calls only counters; ML job items contain top-level
`grafanaApiKey`, dropped before the unchanged structural credential guard. Nested keys and other
known credential fields remain rejected. No integration-list, job-expression, outliers or sift route
is admitted. All identities, names, URLs, keys and arbitrary settings are discarded from outputs.
Faro ingest keys/endpoints are public ingest values, but still not retained. AWS backend write
isolation remains unknown despite GET-only collection; other providers are unknown, not zero, and
there is no all-provider total. PDC's same read action also reaches tokens GET, which the collector
never calls; no connection POST is permitted. Positive staff reader/Admin controls establish the
recorded populations, not universal visibility, strict minimality or a customer deployment grant.
Raw receipt is transient, not memory erasure; caller deadlines do not terminate surviving reads.

Synthetic uses guarded GET `/api/datasources/proxy/uid/<discovered uid>/sm/check/list` and
`.../sm/probe/list` with the separately selected query token. Only counts by bounded check type,
enabled state and public/private probe class leave the source. Targets, scripts, headers, labels
and identities are discarded. These are inventory counts, not probe usage or execution results.

### Default-off label inventory collection

The base T2 source uses the existing metrics/logs/traces/profiles reader scopes, not
new per-stack grants. It calls exact-200 GET Mimir
`/api/prom/api/v1/cardinality/label_names`, Loki `/loki/api/v1/labels` and
`/loki/api/v1/label/{name}/values`, and Tempo `/tempo/api/v2/search/tags` and
`/tempo/api/v2/search/tag/{scope.name}/values`. Only Pyroscope
`/querier.v1.QuerierService/LabelNames` and `/querier.v1.QuerierService/LabelValues`
may use POST, exclusively through `label_risk.profile_read`'s existing fence.
Mimir counts are head-only; the others are bounded 24-hour samples. Current base does
not activate series/index/config/intrinsic-name extensions just because they were witnessed.
The implemented extensions separately add capped Mimir `cardinality/label_values` head
reductions, selected 24-hour Loki `/series` label counts, and one bounded Tempo intrinsic
name-value read in an existing trace slot. These retain numeric lower bounds and closed
non-PII shapes, not value or metric-name strings. Selected Loki counts cannot establish a
whole-label ratio denominator or a below-threshold pass. Tempo overrides and unverified
Loki/Tempo policies remain parked and excluded from applicable weight; readable APIs do
not verify scoring policy. No configuration route or additional permission is enabled.

S3 views and the private hydration input alone may hold minimized names, distinct-value
counts (`exact`/`at_least`), closed non-PII shape counts (`uuid`, `hex_id`, `epoch`,
`url_with_id`, `long_value`) and measured series/stream counts. These items never go to
Loki, finding events, metrics, stdout, `--out` or errors. No raw values or email/IP/phone/
JWT/card shapes persist on this path; PII and >512-byte names become class/count only.
`label_risk`'s separate retention-governed exception is not widened. Unsupported or missing
inputs remain absent, never defaults, zeros or a privacy/completeness claim.
Default-off enablement and tunables add no permission. Source caller-wait budgeting
cannot establish response/process-memory bounds or tenant-wide visibility.

### Labelling witness boundary (2026-10-07)

Staff slugs robknight, portina, portinapushtests, rkaidev and robk were each queried
with staff Admin positive controls and the deployed org reader. This proves operational
sufficiency of that reader, not isolated minimum scopes or universal visibility.

| Exact GET route | Witness and collector boundary |
|---|---|
| `/api/prom/api/v1/cardinality/label_names` and `/api/prom/api/v1/cardinality/label_values` | Admin/reader exact 200 all five under existing metrics reader; selected `__name__` witnessed on nonempty stacks, portinapushtests measured empty. Bounded cardinality/series counts, not exhaustive values; names hit 500 on robknight and robk. |
| `/loki/api/v1/series`, `/loki/api/v1/index/stats`, `/loki/api/v1/index/volume` | Admin/reader exact 200 all five under existing logs reader. One-hour service_name selection only; label-set, numeric count and vector schemas respectively. Stats approximate, no ingesters; volume limit 20 reached on robknight, portina and robk. Not whole-estate ingest. |
| `/config/tenant/v1/limits` | Admin/reader exact 200 all five; chosen legacy effective tenant route. YAML/text/plain, not JSON. OTLP mapping, service-name list and discovery/volume booleans witnessed; missing allow_structured_metadata/max_label_names_per_series remain unknown. Shipping YAML parsing supports retention only, not OTLP subtree parsing or new YAML features. |
| `/loki/api/v1/config/limits/applied` | Admin exact 200 YAML even AcceptJSON; reader 401 invalid_scope all five. Official self-serve docs require logs WRITE, outside D-LBL11 READ-only authority. Not approved for collector, no scope added. |
| `/tempo/api/v2/search/tag/name/values` | Admin/reader exact 200 all five under existing traces reader; typed string objects, 24-hour limit 500, counts 500/7/0/49/500 in the staff order above. Two at limit; below-limit counts do not prove completeness. Documented 1MB default cap not live-config verified. Names remain approved. |
| `/tempo/api/overrides?scope=merged` and `/tempo/status/overrides/{staff_tenant}` | robk reader user route 404; tenant-specific effective route Admin/reader 404. Unreadable, not empty; infer no field absence. Overrides parked, override-dependent rules excluded. No override route grant follows. |

No D-LBL11 policy change or credential remint occurred, so no new policy object IDs exist.
Root-only scope changes still require a fresh policy witness, READ-only scope and readback;
these failures do not authorize WRITE. Witness-first exact paths, no log-line reads and
D-LBL1 retention/minimization are preserved. Raw values are not reproduced here and
staff observations confer no additional customer grant. Detailed evidence and upstream
contracts: /Users/rob/repos/grafana-cloud-org-insights/docs/traps.md, labelling route witnesses.
These observations do not change the implementation-inventory scope table above.

### Loki retention

Effective tenant limits come from `/config/tenant/v1/limits` on the Loki dataplane under the existing
org CAP and `logs:read`. The path has no `/loki` prefix. The deprecated
`/loki/api/v1/config/limits/applied` route requires logs WRITE according to official
self-serve docs, returned reader 401 invalid_scope on all five staff stacks, and is not used
or approved for the collector. Self-serve change
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
 k6 runs API is reachable. This is historical metadata evidence. Current optional count contracts
 are above; k6 still has no admitted collector route.
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
 The separately owner-approved `synthetic-monitoring-query` exception above addresses only the
 single live-discovered datasource UID. The earlier denial is historical; fresh deployed-reader
 two-stack count proof remains unverified. No separate Synthetic API token is minted. See the
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
