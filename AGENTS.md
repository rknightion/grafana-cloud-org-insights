# grafana-cloud-org-insights

Estate-wide insight for a large Grafana Cloud organisation.

## The golden rule: the estate is DISCOVERED every run, never configured

As stacks are added or removed the data must follow with no code or config change. This outranks
convenience everywhere in this project.

The pattern every collector copies: call `gcom.fetch_inventory` fresh, iterate the live stacks, and
treat any per-stack payload as a left-join lookup. Never iterate the payload, and never key a rollup
off anything but the live inventory.

- Never a literal list of stacks or regions. Regions come from the live inventory unioned with the
  three control-plane realms in `gcom.POLICY_REALMS` (`us` holds this project's own reader and is not
  any stack's `regionSlug`, so it can never be derived). Dashboard stack sets are PromQL; a `$stack`
  variable comes from Mimir label values.
- Anything that republishes state re-checks the estate. Carry-forward takes the live stack set and
  drops carried series whose `stack` label has left the org. An empty stack set means unknown, never
  an estate of zero, so a failed inventory call must not blank every per-stack series.
- Inventory and provisioning state do not belong in a config store; per-stack service-account state is
  itself live-queryable. A config store is only for genuine policy: an opt-out list of stacks the org
  asks you to skip, and tunables.
- `collector/emit/budget.py`'s `STACK` constant is the one accepted literal. Cardinality planning
  only, and it never reaches published output.

## Hard rules

- Emit natively: Loki push and Mimir remote_write, never via the OTLP gateway. Routing our own
  telemetry through the org's gateway inflates their gateway request counts and corrupts the
  protocol-adoption numbers this platform then publishes.
- `collector/httpclient.py` refuses any method other than GET. Read-only by construction, and that
  property is load-bearing in what you can tell an org about what this runs.
- Source HTTP deadlines fence caller waits, including DNS and complete reads, through
  `collector/netbound.py`. They do not terminate surviving daemon reads or bound response memory.
  The fixed pool accounts for survivors; publishers are outside this read-source fence.
- Metric labels carry bounded dimensions only: `stack`, `region`, fixed enums. Metric names, dashboard
  uids, user identities and rule names never become labels. Identity-bearing detail may enter Loki or
  S3 only when the deployment explicitly accepts it and enforces minimization, access control,
  encryption and retention for those stores. Cardinality safety is not that privacy decision.
  D-LBL1: `label_inventory` may persist the following in S3 views and the private
  `label_inventory` hydration input only: label and attribute NAMES; distinct-value counts
  (`exact` or `at_least`); closed non-PII value-shape class counts (uuid, hex_id, epoch,
  url_with_id, long_value); series and stream counts. These items never go to Loki, finding
  events, metric labels, stdout, `--out` or errors. A name over 512 bytes, or one matching a
  `pii` key or value class, persists only as a class and a count. Raw values are transient and
  never written. The GCI-0018 raw-value exception is not widened.
- Every metric a pillar emits is declared in `budget.py`'s `CATALOGUE`, or `tests/test_budget.py`
  fails. A per-stack metric costs one series per live stack multiplied by every bounded enum
  dimension, so it has to justify itself by needing a time series: a trend, an alert, or a Grafana
  time-range interaction. Anything point-in-time is a view, which costs nothing.
- The series denominator is the write stack, never the org. Everything lands on one stack, so the org
  figure understates the footprint by roughly the number of stacks in the org.
- A gap is an absent series, never a zero. A pillar must not emit a metric it cannot compute: an
  hourly tier writing a structural zero overwrites the real value a slower tier published, and
  carry-forward correctly refuses to rescue a series the live tier claims to own.
- A view whose inputs are unsatisfied is withheld, never written. The last good copy stays on the
  bucket with its own older timestamp. Visibly stale beats silently wrong.
- A limited run cannot publish. `--limit` and `--stack` compose estate rollups over a subset, so
  `scan.py` refuses every S3, Mimir and Loki write unless `--dry-run` is also set. Without that guard
  a two-stack debug run publishes a two-row table that reads as a finding about the whole estate.
- Minting a service account on a stack is a write on a live customer system. Explicit, idempotent,
  logged, and recorded for teardown, never implicit in a collector.
- Teardown and reconciliation key on recorded object IDs, never on a name pattern. A name-matching
  teardown deleted the provisioning account and orphaned the custom role it was the only identity able
  to remove.
- Never touch an access policy this project did not create. Surfacing the org's own teams' policies is
  the deliverable; changing them is not.
- Alert rules deploy paused and unrouted, and activation requires an explicit receiver. The write
  stack's contact points can include production ticketing, and a rule with `notification_settings`
  unset inherits its notification policy, so an unpaused rule can raise a real ticket because a
  scanner was late. `bin/alerts.py --publish` preserves an existing rule's pause state and routing and
  a new rule still lands paused and unrouted; confirm live state after any publish.
- The per-stack reader stays basic-role-None and query-scoped. Compare role drift as action/scope
  pairs. `datasources:read` may use `datasources:*`; `datasources:query` stays pinned to
  `datasources:uid:grafanacloud-usage-insights`, with one owner-approved S-SM exception: the opt-in
  `synthetic-monitoring-query` token, requiring `synthetic-monitoring`, adds query access only to
  that stack's single live-discovered Synthetic Monitoring datasource uid (plugin type
  `synthetic-monitoring-datasource`) and adds
  `grafana-synthetic-monitoring-app.probes:read` with empty scope. Never a wildcard, name match or
  a grant through the existing `synthetic-monitoring` token, whose three pairs stay unchanged.
  An ambiguous datasource set or a uid outside `^[A-Za-z0-9_-]{1,40}$` adds no query pair. Every
  other datasource query pair and every SM write action remain refused. S-SM(e'): without the new
  token, a held `datasources:query` pair outside an approved telemetry query permits one bounded
  discovery of the datasource list. The approved telemetry query baseline is usage-insights on every
  stack plus `datasources:uid:grafanacloud-usage` only on the write stack, preserving the existing
  desired/removable/dangerous rules for that pair. Only a held pair whose uid equals the uniquely
  discovered, regex-valid SM uid (plus the
  empty-scope probes read action) is removable. Ambiguous or invalid discovery removes nothing and
  reports it; every other query pair stays dangerous. A v0.4.3-correct role makes zero discovery
  calls. With the token absent, scans make zero SM calls.
- The owner's GCI-0041 scope decision accepts two residual risks only for its named routes:
  IRM `grafana-irm-app.integrations:read` also reaches secret-bearing integration configuration,
  but the collector may call only `alert_receive_channels/counters` and publish counts; ML
  `grafana-ml-app.forecasting:read` job items contain `grafanaApiKey`, which must be dropped at
  parse, never logged or persisted. This is not approval for IRM integration lists, alert-group
  lists or schedules, nor a blanket product-route or POST exception. Other approved families
  require their exact-pair and route witnesses before implementation. No standing customer grant
  follows. Rob's loop11 D-CUST11 owner decision (2026-10-03) separately authorizes the customer
  deployment to enable only opt-in readers shipped in v0.6.0 and proven live on dev in that loop:
  Synthetic Monitoring query, Faro apps, ML jobs, AWS accounts, PDC networks, reports and IRM
  integration counters. IRM qualifies only after GCI-0087's exact-200 correction is accepted and
  shipped. The decision preserves every reader-role, route, privacy and publication hard rule;
  unshipped or unproven families receive no customer grant.
- Current main's optional `faro-apps`, `ml-jobs`, `cloud-accounts`, `pdc-networks` and `reports`
  readers are default-off count-only GET sources. They require exact HTTP 200; an otherwise valid
  HTTP 206 body is unavailable, not a complete inventory. Do not globally redefine `Response.ok`
  to enforce this source contract. The AWS `cloud-accounts` route alone treats exact HTTP 200
  with a parsed body containing only `{"data": null}` as available with account count zero,
  under the owner's D-AWS13 complete-empty witness. Other null placements, extra keys, error
  bodies and non-200 responses remain unavailable; this is not generic null normalization.
  `irm-integrations` now also requires exact HTTP 200 at its
  source boundary; valid 206 JSON is unavailable and cannot overwrite its last-good view. GCI-0087
  was accepted under Rob's separately granted loop11 D-IRM11 allowance, not an automatic reset of
  GCI-0074's exhausted review budget.
- Current main's `playlists` and `irm-alert-groups` readers are default-off, count-only GET
  sources requiring exact HTTP 200. They are not shipped in v0.6.0. Playlist counts configured
  objects, not execution or activity. IRM stats expose a bounded canonical count with `exact` or
  `at_least` semantics and `api_default_window`, never lifetime or status-filtered claims. Each
  input adds eight planned series to existing provenance age/availability metrics across four
  tiers; neither adds a product metric. The default-off `library-panels` T2 reader now publishes configured-object counts only. It
  first requires same-token effective `library.panels:read@folders:*` and baseline
  `folders:read@folders:*`, then exact-200 reconciled collection pages. A staff basic-None/Admin
  positive control including a non-General folder supports those witnessed pairs, not universal
  visibility. Unavailable or incomplete coverage stays absent and preserves the last-good view;
  models, targets, creators and IDs remain transient. Its one input adds eight planned existing
  provenance-series combinations, no product metric. Shipping confers no customer enablement grant.
- PDC counts only policies with the exact current stack realm and `set:pdc-signing`, after complete
  reads across `gcom.policy_regions(live_inventory)` and validated pages. Never trust server realm
  filtering, follow a supplied continuation URL with a credential, or call tokens/connection routes.
  Reports counts configured objects, including disabled reports, not executions or delivery.
- Adaptive segmentation discovery is unsegmented, segmented or unknown. A default-only value cannot
  establish whole-stack savings or maturity for segmented/unknown/legacy inputs. Positive segment
  marginal counts do not establish disjointness or fallback additivity; no combined saving is emitted.
- A repair must not re-mint a working credential. Token names are organisation-wide unique, so an
  unnecessary mint can leave an untracked credential while SSM points at the replacement.
- Adaptive savings require verbose recommendation counts. Sum positive marginal reductions for `add`
  and `update`; never use the whole active-series count as the saving.
- Currency is absent when it cannot be priced. A missing or partially priced rate card must not
  manufacture a zero or label a subtotal as the estate total. Metrics use `base_rate_only`, which
  explicitly excludes DPM, or `dpm_aware`, which applies the contracted included-DPM divisor per
  stack.

## Labelling inventory (D-LBL1..11)

The approved source is doc-0008 Part 1 (Labelling best-practice research and rulebook).

- **D-LBL1 Retention.** The identity-bearing detail rule above governs `label_inventory`.
  Raw values are transient and never written; the existing raw-value exception is not widened.
- **D-LBL2 Deterministic only.** No LLM in the scanner or operator tooling. Judgement rules
  are catalogued and excluded from applicable weight.
- **D-LBL3 Layered, tunable thresholds.** Published limits are hard rules. The Professional
  Services bands are the defaults: metrics warn at 100, high at 1,000, critical at 10,000;
  Loki dynamic labels warn at 100+. Everything else is policy. Each threshold carries a
  provenance tag (`published`, `ps` or `policy`) and a source URL, and is overridable through
  the tunables.
- **D-LBL4 Presentation.** Per stack and signal: findings by severity, rules evaluated vs
  passed, a 0-100 score, and the coverage figure. The score is computed only at coverage of
  0.8 or more; otherwise it is absent.
- **D-LBL5 Maturity.** The labelling score replaces `cardinality_discipline`. This waits for
  the dev proof.
- **D-LBL6 Routes.** Staff witnesses are approved for Mimir `cardinality/label_values` and
  `label_names` (limit/selector); Loki `/series`, `index/stats` and `index/volume`; Loki applied
  limits/OTLP config; Tempo intrinsic `name` values and Tempo overrides. Each route is
  implemented only after its witness. A parked route's rules are excluded from applicable
  weight. Calls returning log lines are never covered: never `query`, `query_range` or `tail`.
  The exact approved witness paths are Mimir `/api/prom/api/v1/cardinality/label_names` and
  `/api/prom/api/v1/cardinality/label_values`; Loki `/loki/api/v1/series`,
  `/loki/api/v1/index/stats`, `/loki/api/v1/index/volume`,
  `/config/tenant/v1/limits`; Tempo `/tempo/api/v2/search/tag/name/values`.
  The 2026-10-07 witnesses queried staff slugs robknight, portina, portinapushtests,
  rkaidev and robk with Admin controls and the deployed reader. These successful reads
  prove bounded coverage, not complete inventories. The applied route
  `/loki/api/v1/config/limits/applied` is NOT approved for the collector: reader 401
  invalid_scope on all five and official docs require logs WRITE, outside D-LBL11.
  Choose legacy tenant limits (reader 200 all five); absent fields remain unknown.
  Shipping YAML parsing supports retention only, not OTLP subtrees or new YAML features.
  Tempo overrides remain parked: robk `/tempo/api/overrides?scope=merged` and
  `/tempo/status/overrides/{staff_tenant}` returned 404; infer no field absence and exclude
  override-dependent rules. No overrides implementation is granted until a readable exact
  route witness passes and the path is appended here. No scope was added or credential
  re-minted. Detailed limitations are in
  /Users/rob/repos/grafana-cloud-org-insights/docs/traps.md. The family names are not wildcard
  route grants. Pyroscope is limited to the two exact
  RPC paths and `label_risk.profile_read` fence in the bounded daily label privacy risk section.
- **D-LBL7 Customer grant.** The customer deployment may enable `label-inventory` once it
  ships in a release and the task K dev proof is recorded. No further owner decision is needed.
  Routes without a passing witness are not covered. Every reader-role, route, privacy and
  publication rule is preserved.
- **D-LBL8 Fairness.** Cardinality bands apply only to metrics and streams above a size floor
  (tunable, same pattern as `CARDINALITY_MIN_SERIES`). A static-infrastructure allowlist
  (host, cluster, namespace, node and similar) has its own higher band.
- **D-LBL9 PII shapes.** Email, ip, phone, jwt and card shapes stay on label_risk's
  retention-governed path. The labelling register refers to `risk_label_hygiene` and does not
  duplicate them.
- **D-LBL10 Witness stacks.** Witnesses may query all five staff stacks and choose or combine
  evidence. Each recorded witness names the stack slug.
- **D-LBL11 Pre-approved read scopes.** When a witness shows the org reader lacks a READ
  scope for an approved route, only the root may add that one read-only scope to this project's
  own access policy, after a fresh policy witness and with readback. The addition is recorded
  with its object ID, and the capability document
  is updated. Write or admin scopes, other policies and the per-stack reader role are never
  covered. A new scope can 401 for about 46 minutes; wait it out, never re-mint.

Not amended: `MAX_PER_STACK_FANOUT`, the one-extra-label rule, gap-is-absent, the limited-run
guard, own-input hydration and derived `VIEW_INPUTS`.

## Hydration: every tier composes from the FULL input set

`collector/emit/hydrate.py`. A tier hydrates the inputs it lacks from `scans/<tier>/latest.json`, so
every run publishes a complete view set rather than flattening views only a slower tier can compute.

- `INPUT_OWNER` says which tier gathers each input. Inventory is never hydrated: a tier with no
  inventory has nothing to compose.
- A tier never hydrates its own input from its own last scan. That would make a broken gatherer look
  healthy indefinitely.
- `VIEW_INPUTS` is derived, not hand-written: composing every subset of the optional inputs against
  the synthetic compose fixture and recording the minimal subset that reproduces the full output byte
  for byte. A test re-derives it and fails on drift. Hand-editing the table reintroduces the exact
  defect it exists to prevent, where a pillar gains a dependency, the table does not, and a tier that
  cannot compute the view publishes it as zeros.
- Hydration and carry share `carry.MAX_FUTURE_SKEW`: timestamps up to five minutes in the future
  are admitted as age zero; greater skew is unavailable with `future_timestamp` provenance.
  Unavailable future inputs withhold dependent views and preserve the last-good object; they
  never publish a usable freshness-age gauge. Schema-version and own-input rules are unchanged.
- `MAX_INPUT_AGE` is deliberately the same constant as `carry.MAX_CARRY_AGE`. One staleness story.
  Two constants that can drift apart would mean a view withheld while its metric is still carried, or
  the reverse.
- Per-input provenance rides in every view's `meta.inputs` and in the input-age metrics. The
  dashboards read the age of the INPUT, not of the run: they differ by hours, and the input age is
  what governs how current a figure is.

## Dashboards

`collector/dashboards/build.py` is the panel library and holds the `DASHBOARDS` registry;
`bin/dashboards.py` holds the per-dashboard definitions plus `BUILDERS` and `PILLAR_OF`. A new
dashboard must be added to all three or it loses its cross-links or fails to build.

`operations` and `commercial` read `grafanacloud-usage` only: panels, no collector code, no
credential, zero series. `ai` mixes both sources and its banner says so, because neither standard
banner is true there. `dashboards` (Pillar J) reads each stack's own `grafanacloud-usage-insights`
datasource with that stack's reader token and the mandatory `instance_id` guard in
`collector/sources/usage_insights.py`; a selector without that filter silently attributes another
stack's logs.

## Task interface

`just check` is the gate and is exactly what CI enforces. The suite runs with no AWS credentials, no
network and no live estate, so run and rerun it freely.

`just publish-image` is `[confirm]`-gated and pushes a real image to the configured ECR repository.
Never pass `--yes` or `JUST_YES=1` to get past that gate.

`testdata/` is a synthetic estate and `tests/fixtures/` a synthetic scan. Read `testdata/README.md`
before treating any number in either as a measurement.

Four kinds of test here are required because each catches a class of bug that looks like working code:

- Contract tests that read a real artifact back. A test written from the implementation cannot catch
  the implementation being wrong about an external contract.
- Tests that re-derive a declared table from live data rather than asserting the table's contents.
  `VIEW_INPUTS` and the empty-view schemas are both in this category.
- Coverage gates over assembled dashboards: every published view is rendered and every declared metric
  is rendered or alerted. Exemptions need an explicit reason.
- Fixture hygiene as a security boundary. Live compose exports go to a separate path and are
  anonymised before use; the exporter refuses to overwrite the committed fixture.

## Deeper references

- `docs/traps.md` - read before writing a panel, a PromQL expression, an Infinity query or a collector
  source. Live-verified behaviour, mostly cases where a wrong call returns HTTP 200 and a wrong answer.
- `SPEC.md` - capability model, architecture, correlation traps, security posture.
- `CAPABILITIES.md` - what an org-realm token reaches and what it does not, endpoint by endpoint.
- `RUNBOOK.md` - read before running, rotating, rolling back or tearing down a deployment.
- `BUDGET.md` - the declared metric catalogue, generated from `collector/emit/budget.py`; never
  hand-edited.
- `terraform/README.md` - read before changing the module or ordering a first deployment.
- `LOOP.md` - read at loop preparation: gates, release rules, environments and credential conventions, standing route exceptions, traps, cross-harness eligibility, resource mutexes and Grafana stacks for this repository's loops.

## Bounded daily label privacy risk (GCI-0018)

`collector/sources/label_risk.py` and `collector/sources/label_inventory.py` may POST only
`/querier.v1.QuerierService/LabelNames` and `/querier.v1.QuerierService/LabelValues`, the two
exact Pyroscope read RPCs, on each live inventory `hpInstanceUrl`, with `hpInstanceId`.
They do so only through `label_risk.profile_read`, which keeps the exact path set, the
inventory HTTPS host, no redirects and the bounded body and response. No other module,
path or helper is granted by this exception, and `collector/httpclient.py` stays GET-only.
This dedicated two-route
exception is separate from `collector/sources/dataplane.py`'s `CONNECT_RPC_READ_ROUTES` helper:
Fleet `/collector.v1.CollectorService/ListCollectors`, Fleet
`/pipeline.v1.PipelineService/ListPipelines`, and Pyroscope
`/querier.v1.QuerierService/LabelValues`. The helper admits only these exact parsed-path suffixes
over HTTPS without redirects, with a nonempty host and no userinfo, query, fragment or percent-encoded
path. No other path or method is granted. `collector/httpclient.py` remains GET-only. Clear classified matches are approved
only in `risk_label_hygiene` and the private `label_risk` hydration input, never in Loki, stdout,
diagnostic `--out`, errors or metric labels. Ordinary/unmatched values and decoded JWT claims
are transient. This is a bounded daily label-API sample, never an exhaustive privacy audit.

Raw-match retention uses `scan_retention_days` (positive whole days, default 90) for current
`scans/` objects and the reserved full-key prefix `views/risk_label_hygiene.json` in the same
bucket lifecycle configuration. Do not reuse that prefix for other keys or expire all views.
Eligibility starts at last publication; hydration resets it. Current expiry is followed by
seven-day noncurrent-version expiry and asynchronous AWS processing, not strict erasure
90 days from observation. Other last-good views and IAM remain unchanged. For adopted buckets
(`create_bucket = false`), owners must configure equivalent targeted retention in the existing
lifecycle policy before raw publication; root must verify effective retention, versioning,
encryption and reader access. This includes a fresh effective bucket-policy witness denying
non-TLS access. A missing policy blocks raw publication; a lifecycle grant does not authorize
adding a bucket policy. Never add a competing lifecycle configuration resource.
