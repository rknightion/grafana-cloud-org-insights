# Credentials and permissions

Separate org reader, runtime writer, provisioner, stack-local readers and short-lived publication
credentials, each with the smallest declared scope that does its job. This page records which identity reaches each source.

Endpoint availability varies by plan, region and product rollout, so a deployment records the actual HTTP status and coverage rather than turning an unavailable source into a zero.

## Creating the policies: realm decides the region

Access policies are regional objects, and `POST /api/v1/accesspolicies` takes the region as a query parameter. Which region is not a free choice, and picking the wrong one does not fail at creation - it fails later as a 404 or an empty list, which reads as a missing resource rather than a misplaced credential.

- An **org-realm** policy belongs to the organisation's own region, which is **not necessarily the region its stacks are in**. An organisation whose stacks all live in one region can still hold its org-realm policies somewhere else entirely.
- A **stack-realm** policy belongs to that stack's `regionSlug`, from `GET /api/orgs/<org-id>/instances`.

List the organisation's existing policies before creating any, and put a new org-realm policy in whichever region the existing org-realm policies already use. That is the only reliable way to discover it.

Region does not constrain what an org-realm token can then reach: it reaches every region's data plane. It only determines where the policy object lives.

## The org-realm reader

`collector.config.READER_SCOPES` is authoritative. One org-realm token reaches all four signal databases in every region of the estate - the region hint in the token payload does not constrain the data plane.

| Scope | Routes this collector calls, not the scope boundary | Basic-auth user |
|---|---|---|
| `stacks:read` | Grafana.com stack inventory | bearer |
| `stack-users:read` | per-stack users through Grafana.com | bearer |
| `stack-plugins:read` | per-stack plugins through Grafana.com | bearer |
| `org-members:read` | organisation membership | bearer |
| `accesspolicies:read` | regional access-policy inventory | bearer |
| `metrics:read` | Mimir cardinality API **and the whole Prometheus query API** | `hmInstancePromId` |
| `logs:read` | Loki label and label-value endpoints plus effective tenant limits | `hlInstanceId` |
| `traces:read` | Tempo search-tag endpoints | `htInstanceId` |
| `profiles:read` | Pyroscope label inventory; label-risk `LabelNames` and `LabelValues` | `hpInstanceId` |
| `rules:read` | Prometheus and Loki ruler inventory | signal instance id |
| `alerts:read` | Alertmanager status, alerts and silences | `amInstanceId` |
| `adaptive-metrics-rules:read` | `/aggregations/rules` | `hmInstancePromId` |
| `adaptive-metrics-recommendations:read` | `/aggregations/recommendations?verbose=true` | `hmInstancePromId` |
| `adaptive-metrics-config:read` | `/aggregations/recommendations/config` | `hmInstancePromId` |
| `fleet-management:read` | Fleet Management Connect-RPC list methods | stack `id` |

The basic-auth user differs per signal and comes from `dataplane.AUTH_FIELD`. Fleet Management and the Alertmanager are the two that do not use a signal instance id.

The route column describes current implementation. It is not a credential boundary. In particular,
`logs:read` is a full Loki read scope and can return log content. It is retained deliberately for the
label inventory, with explicit deployment consent. `CAPABILITIES.md` records
the verified breadth, unverified scope probes and the implementation restraints.

Fleet calls use POST because that is the RPC transport. The daily label-risk source also has an
explicit exception for native Pyroscope `LabelNames` and `LabelValues` POST reads on the inventory
`hpInstanceUrl`. Neither exception permits another path or method; the general HTTP client remains
GET-only. Source caller-wait deadlines include DNS and full reads but cannot terminate surviving
daemon transports or bound response memory.

Grafana.com is paced at six requests per second. Paused stacks are skipped when the control plane answers with its paused-stack conflict response.

Two things the org token deliberately does not have:

- **`adaptive-metrics-exemptions:read` is deliberately absent.** The first path sweep covered 34
  candidates plus deliberate nonexistent controls, and later checks expanded past forty across two
  stacks. The resource is stack-plugin RBAC, not an org access-policy scope. `CAPABILITIES.md` records
  the route evidence and remaining plugin-health probe.
- **`stack-service-accounts:read` does not exist.** Only the write scope does, so it is not given to the collector. Service-account inventory is reached through each stack's local reader instead.

### Content and secret exposure beyond inventory

Read-only is not metadata-only. `metrics:read` reaches Prometheus queries, `logs:read` reaches log
content, and isolated stack-realm probes of `traces:read` and `profiles:read` returned trace and profile
content. Those latter probes do not establish an exhaustive org-realm content boundary. The
collector's restrained routes are an implementation property, not a credential-enforced restriction.
See `CAPABILITIES.md` before consenting to these grants.

`alerts:read` and `rules:read` also expose sensitive payloads:

- **`/alertmanager/api/v2/status` returns the stack's raw Alertmanager configuration** in `config.original`, `http_config` included. Where a stack's contact points live in Alertmanager rather than in Grafana, that YAML can carry webhook URLs and tokens. Nothing derived from that body may be stored, logged or emitted beyond bounded counts.
- **`/api/prom/api/v1/alerts` returns firing instances with their full customer label sets.** Unbounded and identity-bearing. Count them; never carry them into a metric label.
- The Loki ruler answers **404 with `no rule groups found`** when a stack has no rules. That is an empty inventory, not a permission failure. `/prometheus/api/v1/rules` on the same host returns 200 with an empty group list for the same stack, so prefer it and read the 404 as zero.

## The stack-local reader

The provisioner declares `collector.provision.DESIRED_PERMISSIONS`. It creates a basic-role-`None` service account on each stack and assigns `custom:gcinsight.reader`. Drift is compared as action/scope pairs, not action names.

The role can read:

- Assistant aggregate usage, tenant-scoped inventory and investigations counts;
- Adaptive Logs recommendations through the plugin-proxy route;
- retention change requests through the Databases Configuration app resource route;
- service-account inventory and permission metadata;
- datasource metadata and caching state;
- folders, dashboards, public dashboards and snapshots;
- teams, team permissions, team roles, user roles and custom-role metadata;
- alert-rule and receiver inventory, without receiver secrets;
- Adaptive Metrics exemption and Adaptive Traces policy/configuration/recommendation read actions,
  without assigning a plugin role that bundles writes;
- the datasource proxy for exactly `grafanacloud-usage-insights` on every stack, plus exactly
  `grafanacloud-usage` on the nominated write stack for the bounded adoption input.

`datasources:read` uses `datasources:*` because it lists metadata. `datasources:query` is separately
uid-pinned and is never widened to `datasources:*`. The reader cannot query arbitrary production
datasources.

The default-off `GCINSIGHT_READER_PRODUCT_READS` policy accepts `slo` and `synthetic-monitoring`.
It selects additional read action/scope pairs, not a guarantee that every product endpoint works.
Scan and provisioner must use the same policy. Unsetting it removes the optional grants during
reconciliation without replacing a working reader token.

The declaration explicitly refuses decrypted alert secrets, secure values, user session tokens, Grafana auth settings, support bundles, provisioning writes and Adaptive Traces mutation actions. `chats:access` is not granted.

**Several list endpoints return HTTP 200 with a permission-filtered empty list.** Coverage is therefore part of the result, and a zero is trusted only after the matching role pair is confirmed present.

## Write identities

The runtime writer carries only `metrics:write` and `logs:write`, in the nominated write stack's realm. It cannot touch any other stack because the realm forbids it, not because a scope check says so.

The provisioner carries `stacks:read` and `stack-service-accounts:write`, and is a separate opt-in
scheduled task with a separate secret key. Its cadence is daily by module default; deployment
overrides may differ. See the [operator timetable](https://github.com/rknightion/grafana-cloud-org-insights/blob/main/RUNBOOK.md#scheduled-jobs).
The credential can mutate service accounts; the recorded-ID ledger and explicit operator authority,
not a read scope, constrain that write surface.

Build-time Grafana credentials are supplied only to the dashboard and alert publication tools, and
should be short-lived. These tools write dashboards and alert rules on the nominated stack; they are
not runtime collector calls.

## Source-specific contracts

### Bounded label-risk sampling

The daily source samples label names and values across Mimir, Loki, Tempo and Pyroscope using the
existing org reader. It is not an exhaustive privacy audit. Full classified matches may be retained
only in the approved `risk_label_hygiene` S3 view and private `label_risk` hydration input, never in
Loki, stdout, diagnostic `--out`, errors or metric labels. Ordinary values and decoded JWT claims
remain transient. Access, encryption, minimisation and targeted retention must be accepted and
verified before publication; see [Security](security.md).

### Usage insights

Each stack's usage-insights datasource exposes a **regional** tenant, so every query made with that stack's own reader includes `instance_type="grafana"` and `instance_id="<stack id>"`.

The label is the stack `id` for Grafana events, not its Prometheus tenant id. The query helper refuses a selector without `instance_id`. Get it wrong and one stack's figures are repeated across every stack in its region, with nothing failing.

### Adaptive Metrics

`?verbose=true` is required for series counts. The default response is structurally complete-looking and insufficient for savings arithmetic.

### Adaptive Logs

The working read route is the Adaptive Logs plugin proxy. Frontend app resource paths can return 500, and datasource-proxy calls can report authentication failure even when the reader role is correct. Recommendation volume has no declared or settable time window.

### Loki retention

Effective `retention_stream` entries come from the Loki dataplane under the existing org
`logs:read` token. The stack-local reader uses only generic app access for the Databases
Configuration request resource. No datasource-query permission for the production Logs datasource
is granted. The two reads are independent: an empty request list does not prove that no effective
override exists.

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
