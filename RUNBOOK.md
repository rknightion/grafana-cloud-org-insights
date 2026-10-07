# Runbook - estate insights platform

## Label inventory policy interface (default off)

Frozen handoff for composition: `Config.label_inventory_tunables` is the evaluator-ready
mapping (`size_floor=100`, `static_multiplier=10`, `coverage_floor=0.8`, `thresholds={}`).
The producer accepts `compose.build_all(..., label_inventory_tunables=None)` and passes
that mapping to `label_rules.evaluate(..., tunables=...)` and threshold provenance.
All composing tiers forward it; policy is not stored in the frozen private input schema.
`Config.label_inventory_static_names` is a tuple passed via `probe_all(static_names=...)`
to each `probe_stack`; `Config.label_inventory_budget_seconds` is passed as `max_seconds`.
Defaults preserve the existing static-infrastructure names and 900-second ceiling.
The source still takes at most a quarter of remaining T2 time after label_risk.

Deployment environment: `GCINSIGHT_LABEL_INVENTORY_ENABLED` (default `0`),
`GCINSIGHT_LABEL_INVENTORY_TUNABLES` (JSON evaluator mapping, default `{}`),
`GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES` (JSON unique name list, at most 64 entries),
and `GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS` (finite seconds, >0 and <=900).
Coverage can be raised to 1 but never lowered below 0.8. Size floor and static multiplier
are positive whole numbers. Threshold overrides must name catalogue rules, supply every
existing band, stay positive and ordered, and cannot override published hard limits.
Tuned bands retain the source URL as rationale but carry policy provenance.
No setting adds a permission, widens a response cap or promises bounded process memory.
The existing shared opt-out policy remains unchanged.

Explicit consumers: old manifests with the entire new field group absent retain their old
digests/defaults. Explicit regenerate/upgrade supplies the new defaults and new digests;
check rejects partial groups. Regenerate explicitly fills missing new fields.
Old digests remain valid with module-injected new fields only at their exact canonical defaults.
Wire every new module variable from that projection before
using the regenerated manifest; check never silently rewrites a deployment.

## Read-only labelling stability evidence v1

Verify already captured local evidence with
`just verify-labelling-stability "$LABELLING_STABILITY_EVIDENCE"`.
This is the `verify-cmd` for the later natural-T2 proof, not permission to run a task,
read a live tenant, change schedules, fetch credentials or modify evidence. The recipe
makes no AWS/HTTP calls and disables Python bytecode writes. It reads at most 32 daily
observations, each JSON artifact <=64 MiB, with a 60-second CPU bound. Relative artifact
paths resolve against the supplied evidence file's directory. Errors print no payload.
The fixture test exercises synthetic artifacts only; it is not a development stability proof.

The selected evidence JSON has this contract (all named fields are required except tunables):

```json
{
  "v": 1,
  "source_sha": "<full lowercase tested source SHA>",
  "image_digest": "sha256:<64 lowercase hex>",
  "catalogue_version": 1,
  "runtime_projection_digest": "<64 lowercase hex, actual scan runtime projection>",
  "deadline_seconds": 3600,
  "max_score_delta": 5,
  "tunables": {},
  "observations": [
    {
      "source_sha": "<same tested SHA>",
      "image_digest": "sha256:<same immutable digest>",
      "catalogue_version": 1,
      "runtime_projection_digest": "<same verified scan projection digest>",
      "task_arn": "<exact natural T2 task ARN>",
      "container_name": "<collector container name>",
      "scan_path": "<exact downloaded published scan envelope bytes, not a re-serialization>",
      "publication_path": "<captured version-specific GetObject request/response and downloaded-body digest>",
      "stopped_path": "<local describe-tasks STOPPED JSON>",
      "schedule_path": "<actual GetSchedule response captured for this invocation>",
      "launch_path": "<captured CloudTrail ECS RunTask event, or one-event Records array>",
      "task_definition_path": "<actual describe-task-definition response for this revision>",
      "memory_path": "<local measured memory witness JSON>"
    }
  ]
}
```

Repeat observations in chronological order, with at least three observations spanning
>=48 hours and consecutive UTC calendar days, each 23..25 hours apart. Two dated files
only 24 hours apart cannot establish a 48-hour span. `max_score_delta` is the caller's
explicit acceptance tolerance in score points (0..100), not a published Grafana limit;
the example 5 is illustrative, not an owner decision. `tunables` is the archived evaluator
policy used by these runs; a changed policy needs a new comparable evidence set. Source
SHA comes from the reviewed immutable build record, not an invented scan field. Image
identity must also match the actual collector container's stopped descriptor. The
catalogue version must match the current accepted catalogue. Do not manufacture source,
scheduling, publication or memory witnesses to satisfy this interface.

`stopped_path` is the actual AWS describe-tasks response: no failures, exactly one task,
matching `taskArn`, `lastStatus=STOPPED`, timezone-bearing `startedAt`/`stoppedAt`, task
`memory` in MiB, and `containers` with exact integer `exitCode=0`; the named collector
also has the matching `imageDigest`. Every task is distinct. Task elapsed time and the
scan's measured `meta.duration_seconds` must be positive and <=`deadline_seconds` (<=3600).
The scan is an actual T2 envelope with healthy sources/scan, generated and published
within that task's window; future stopped times beyond five minutes are rejected.
Publication time and object identity must come from the bound object witness below,
not a caller timestamp or a privacy/publication pass bit.

`publication_path` contains a captured **version-specific successful GetObject** request
and its unmodified response metadata, plus the SHA256 measured over its downloaded body:

```json
{
  "request": {"Bucket": "<captured scan runtime bucket>", "Key": "<timestamped scans/t2 object key>", "VersionId": "<non-null object version>"},
  "response": {
    "VersionId": "<same requested version>",
    "ETag": "<actual quoted S3 ETag>",
    "LastModified": "<actual timezone-bearing object modification time>",
    "ContentLength": 1234,
    "ServerSideEncryption": "AES256"
  },
  "body_sha256": "<64 lowercase hex measured over exact downloaded bytes>"
}
```

The bucket must equal the captured task runtime `GCINSIGHT_S3_BUCKET`; the key must equal
`scans/t2/<meta.generated_at with colons/hyphens removed>.json`, exactly the publisher's
timestamped key. `latest.json` is not an immutable observation. Both version IDs must
match and cannot be absent, blank or `null`; the downloaded byte length and SHA256 must
match the witness. A SHA256 declaration alone is not object linkage: the actual S3
response must also bind those bytes via either its quoted single-part MD5 ETag under
SSE-S3 (`ServerSideEncryption=AES256`, no SSE-C), or native `ChecksumSHA256` (base64)
with `ChecksumType=FULL_OBJECT`. Multipart, SSE-KMS and SSE-C ETags are not treated as
MD5; without a native full-object SHA256 they remain unverified. This does not authorize
rewriting an object or changing encryption/checksum settings to manufacture evidence.
`LastModified` must follow the envelope generation and lie within this exact stopped
task's start/stop window. A legacy observation `publication_at`, if supplied, must agree
with that response timestamp but never substitutes for the object witness. Preserve
the exact downloaded bytes: pretty-printing or re-serializing changes the checksum.
These checks authenticate consistency of supplied captured artifacts, not the origin
of arbitrary fabricated local JSON; root retains provenance of the actual AWS capture.

`schedule_path` is an actual GetSchedule response (`Arn`, `State=ENABLED`,
`Target.Arn`, `Target.RoleArn`, `Target.EcsParameters.TaskDefinitionArn`), not an invented
natural-run summary. The cluster and task definition must match the stopped task and the
schedule ARN must be the same across days. `launch_path` must preserve the captured
CloudTrail event (or a `Records` array containing exactly that event):
`eventName=RunTask`, `eventSource=ecs.amazonaws.com`, timezone-bearing `eventTime`,
`userIdentity.sessionContext.sessionIssuer.arn` matching that scheduler target role,
and `userIdentity.invokedBy` or `userAgent` exactly `scheduler.amazonaws.com`.
The actual `requestParameters.cluster`/`taskDefinition` must match, and
`responseElements.tasks` must link exactly one successful launch to this task ARN and
revision, with no failures. `eventTime` supplies the daily invocation date and must
precede task start by <=900 seconds. An unsupported/truncated CloudTrail schema,
missing response linkage or missing service identity is unverified; no new collection
permission or substitute provenance bit is granted by this verifier.

`task_definition_path` is the captured response with `taskDefinition.taskDefinitionArn`
and `containerDefinitions` for the exact revision. The collector image must be digest-pinned;
its actual command (including captured ECS overrides) must select T2 and the declared
deadline. Only exact `--tier`, `--deadline-seconds`, and optional positive-integer
`--concurrency` options are admitted (separate or equals-form values); repeated options,
non-T2, dry-run, limit/stack/subset, diagnostic output, lock bypass, abbreviations and
unknown flags fail closed. The effective captured ECS command includes any container
command override, not just the task-definition default.
Environment overrides are merged before validating the scan runtime projection:
the captured `GCINSIGHT_RUNTIME_CONFIG_DIGEST` must match the shared root/observation
`runtime_projection_digest` and its computed canonical environment digest. Actual label
inventory enablement must be `1`, actual evaluator policy must equal archived `tunables`,
and actual static-name/source-budget policy must stay identical across days. Missing
policy identity or a mismatch is unverified, never silently replaced by default tunables.

`memory_path` contains `task_arn`, `method`, `peak_bytes`, `limit_bytes`, `window_start`
and `window_end`. Supported measured methods are `cgroup-memory.peak` and
`container-insights-memory-utilized-max`. Preserve the measurement's raw provenance
alongside that witness. The window must lie within the same task and cover start/end to
within 60 seconds. Peak must be >0 and <=limit, and limit must equal the actual task's
MiB memory allocation converted to bytes. A sampled Container Insights maximum is a
sampled witness, not an unsampled strict process peak or general memory bound. Missing
memory fails/unverified; do not substitute the configured memory limit for measurement.

The recipe validates every stack's actual `data.label_inventory` through the frozen
minimized schema, with all four signals and at least one non-unavailable signal. Raw
values, unknown fields, PII names/shapes and oversize clear names fail schema validation.
It recomputes same-version scores from these inputs and compares published-score-eligible
stack/signal pairs across each adjacent day, reporting maximum absolute change against
the caller's tolerance. No comparable score pairs is unverified, not stable; departed or
new stack pairs do not become zeros. It reports aggregate evidence only, never names.
This schema check is not a privacy-pass bit or proof of absence in every downstream S3,
Loki, metrics, stdout or error artifact. The separately authorized live proof must collect
those sink checks and per-stack p95 runtime; this local recipe does not fabricate them.

## Standing up a new deployment

Before starting these live phases, follow [Clean-room validation](docs/clean-room-validation.md).
It requires fresh clones, distinguishes Terraform validation from a credentialed plan, and records
the private identifier gate and rollback prerequisites. Stop at the live-change approval gate;
this runbook describes operations but does not grant authority to perform them.

This section is the whole procedure for a named organisation, in the order it must actually happen.
Each phase states what to collect, what to run, and what proves the phase finished. Do not skip
forward: several steps look independent and are not. Phase 6 prepares the per-stack credentials
without which the first T2 scan in phase 7 refuses publication.

### 0. Collect the inputs

Nothing here has a default, deliberately - a default org id or tenant is one deployment's identifiers
silently baked into another's collector. Gather all of it before touching anything:

| Input | Where it comes from |
|---|---|
| org id | `GET https://grafana.com/api/orgs/<org-slug>` |
| write stack: slug, numeric `id`, `url` | `GET https://grafana.com/api/orgs/<org-id>/instances` |
| Mimir url + tenant | the same response: `hmInstancePromUrl`, `hmInstancePromId` |
| Loki url + tenant | the same response: `hlInstanceUrl`, `hlInstanceId` |
| stack region | the same response: `regionSlug` |
| an org admin credential | an existing org-realm token with the scopes to create access policies |

The write stack is a decision, not a lookup. It receives this platform's active series and carries its
dashboards and alert rules. Tell its owner. Measure the footprint with a range query against that stack
alone - the organisation total is not the denominator. Confirm too that the deploying organisation
accepts clear identity data in S3 and Loki.

### 1. Create the four access policies

**Realm decides the region, and getting it wrong is not a validation error - it is a 404 later.** An
org-realm policy is created against the org's own region, which is not necessarily the region its
stacks are in; a stack-realm policy is created against that stack's `regionSlug`. List existing
policies first and copy the region an existing org-realm policy already uses:

```bash
curl -H "Authorization: Bearer $ADMIN" \
  "https://grafana.com/api/v1/accesspolicies?region=<region>&orgId=<org-id>"
```

Then create each policy with `POST https://grafana.com/api/v1/accesspolicies?region=<region>`:

| Policy | Realm | Scopes |
|---|---|---|
| reader | org | every scope in `collector.config.READER_SCOPES` |
| writer | stack, the write stack | `metrics:write`, `logs:write` |
| provisioner | org | `stacks:read`, `stack-service-accounts:write` |
| Firehose logs (optional) | stack, the write stack | `logs:write` |

The Firehose credential is deliberately separate from the writer so the log path can be revoked on its
own. Mint one token per policy with `POST https://grafana.com/api/v1/tokens?region=<region>` and record
the policy ids - a consumer manifest declares them.

An org-realm token reaches every region's data plane; the region in the token payload is a hint, not a
boundary. Verify the reader before going further: any authenticated call that lists the estate proves
the realm and the scopes at once.

### 2. Create the insights folder on the write stack

The dashboard builder resolves the folder **by title** and fails if it does not exist, while the alert
builder addresses it **by uid**. So it has to exist first, and its uid has to be recorded.

Stack API calls need a Grafana credential, not a cloud access policy token. Create a short-lived Admin
service account through grafana.com's stack proxy, use it for phases 2, 8 and 9, and delete it when
they are done - deleting the account revokes its token:

```bash
curl -X POST -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -d '{"name":"gcinsight-build","role":"Admin"}' \
  https://grafana.com/api/instances/<write-stack-slug>/api/serviceaccounts
curl -X POST -H "Authorization: Bearer $ADMIN" -H 'Content-Type: application/json' \
  -d '{"name":"gcinsight-build-<date>","secondsToLive":3600}' \
  https://grafana.com/api/instances/<write-stack-slug>/api/serviceaccounts/<sa-id>/tokens

curl -X POST -H "Authorization: Bearer $BUILD" -H 'Content-Type: application/json' \
  -d '{"title":"<folder title>"}' https://<write-stack-slug>.grafana.net/api/folders
```

The folder title and the recorded uid must match what the deployment configures for
`GCINSIGHT_DASHBOARD_FOLDER_TITLE` and `GCINSIGHT_INSIGHTS_FOLDER_UID`.

### 3. Create the adopted secrets

Only the Firehose access-key secret must exist before the first apply, because Terraform takes its ARN
as an input. Its value is a JSON object with one field:

```json
{"api_key": "<loki-tenant>:<logs-write-token>"}
```

That `<tenant>:<token>` form is what the Grafana AWS-logs endpoint expects, and it is not the same
shape as the collector's multi-key secret - which is why the module cannot select the credential out of
that one.

### 4. First apply, with everything scheduled turned off

For stack-local collection, opt in with `create_provisioner = true` (the module default is false).
Apply with `schedules_enabled = false`, `provisioner_enabled = false` and
`firehose_log_subscription_enabled = false`. Everything exists; nothing fires. Doing this out of order
starts tasks before their credentials and image are ready. The failure frequency follows the
configured schedules, not four runs an hour.

Leave `image` empty on this first apply if the module is creating the ECR repository - there is nothing
to pin yet and the task definitions fall back to `<repo>:latest`.

Then write the collector tokens into the secret the module created, as three JSON keys under the names
the deployment configured for reader, writer and provisioner.

### 5. Build, push and pin the image

Build for the architecture the task definitions declare. An x86 image on an ARM64 task definition fails
at runtime with `exec format error`, not at plan time.

Push, take the returned digest, set it as the image, and apply again so every task definition pins an
immutable reference. `:latest` means a task that fails today and succeeds tomorrow with no change in
configuration, which is the most confusing failure mode a scheduled job has.

### 6. Run the provisioner FIRST, before any scan tier

**This is the step whose ordering is not obvious and whose failure is misread.** Run the provisioner
task by hand and let it reconcile one basic-role-`None` reader service account per stack, writing each
stack's token to SSM under the configured prefix.

Until it has, every stack-local source in T2 returns `no_credential`: service accounts, Assistant,
usage insights, dashboard inventory, datasource query cost, Adaptive Logs, public dashboards and alert
routing all report `0 of N available`, coverage is `0.0`, and T2 exits `1` with
`scan coverage is below the publication floor; REFUSING all S3, Mimir and Loki writes`. That is the
collector behaving correctly - a partial sweep published as a full one looks like an estate that
shrank - but it reads like a broken reader token, and the reader token is fine.

Proof the phase finished: `gcinsight_stacks_provisioned` equals the provisionable stack count,
`gcinsight_stacks_missing_credential` is `0`, and one SSM parameter exists per stack.

Never include the provisioner in a delegated or concurrent scan batch. It holds org-wide
service-account write authority and performs pruning.

### 7. Run the four tiers, serially, in dependency order

T2, then T3, then T1, then T4 - the order in *Manual scans* below, and for the reasons given there.

Verify each from both sides: the ECS task produced a log stream, and `scans/<tier>/latest.json`
advanced and names the expected input keys. Expect earlier tiers to withhold views whose inputs the
later tiers own; by the end of T1 all views with fresh, satisfied inputs should publish. Optional
unavailable inputs still withhold dependent views; check provenance rather than expecting every view
unconditionally. T4 declining to diff is correct on a young deployment - it needs two scans in a
window before it can compute one.

### 8. Wire the Infinity datasource

Mint an access key for the `views/`-only reader IAM identity and configure the datasource on the write
stack. It authenticates with AWS SigV4 against S3:

```json
{
  "name": "<configured datasource name>",
  "type": "yesoreyeram-infinity-datasource",
  "access": "proxy",
  "jsonData": {
    "auth_method": "aws",
    "aws": {"authType": "keys", "region": "<bucket region>", "service": "s3"},
    "allowedHosts": ["https://<bucket>.s3.<bucket region>.amazonaws.com"]
  },
  "secureJsonData": {"awsAccessKey": "<key id>", "awsSecretKey": "<secret>"}
}
```

The datasource name must equal `GCINSIGHT_DASHBOARD_DS_NAME`; the builder resolves it by name. Prove it
with `GET /api/datasources/uid/<uid>/health` before publishing anything.

### 9. Publish dashboards, then alert rules

Dashboards need live views, so this cannot precede phase 7. New alert rules publish paused and
unrouted; ordinary publication preserves existing pause and routing state. Keep new rules paused until the schedules have been on long enough for one run of each tier to land, or
the staleness rules are correctly in breach the moment they are activated.

If a build fails on a missing or empty view, see *Empty or missing views* below. A clean estate's
empty finding lists are supported; a never-published view still needs its owning scan.

Delete the build service account when this phase is done.

### 10. Turn it on, in this order

Firehose log subscription (only after a deliberate test record has been delivered), then the collector
schedules, then the provisioner schedule last - it is the only scheduled job that writes to Grafana's
control plane. Scan tiers write to S3, Mimir and Loki.

Confirm afterwards that any other deployment sharing the account is untouched: its task-definition
revisions, schedule states and image digest should all be unchanged.

## Required runtime configuration

No deployment identifier is defaulted:

`GCINSIGHT_ORG_ID`, `GCINSIGHT_WRITE_STACK`, `GCINSIGHT_MIMIR_URL`,
`GCINSIGHT_MIMIR_TENANT`, `GCINSIGHT_LOKI_URL`, `GCINSIGHT_LOKI_TENANT` and
`GCINSIGHT_S3_BUCKET`.

The collector reads `GCINSIGHT_READ_TOKEN` and `GCINSIGHT_WRITE_TOKEN`. The provisioner
alone reads the provision token. Per-stack reader tokens are SSM `SecureString` values below the
configured prefix.

`GCINSIGHT_EXPECTED_RETENTION_POLICY` is optional deployment policy, supplied by Terraform's
`expected_retention_policy` list. Leave it empty to disable selector-policy findings. See
`docs/configuration.md` for the JSON shape; never put an organisation's selectors in this repository.

`GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL` defaults to `60s` and is supplied by Terraform's
`fleet_default_scrape_interval`. Fleet pipelines scraping faster than it are DPM findings; see
`docs/configuration.md`.

`GCINSIGHT_READER_PRODUCT_READS` defaults to empty. Current main accepts `slo`,
`synthetic-monitoring`, `synthetic-monitoring-query`, `irm-integrations`, `faro-apps`, `ml-jobs`,
`cloud-accounts`, `pdc-networks` and `reports`. An unknown token stops the provisioner before writes.
Use the [family meaning and limits](docs/configuration.md#optional-product-readers) and
[exact route/pair map](CAPABILITIES.md#optional-count-only-product-inputs) before selection. IRM
acceptance is parked on HTTP 206 partial-response handling; it is not an accepted delivered counter.
Scan and provisioner must agree. No customer grant follows from an accepted setting.

Synthetic configuration counts require both SM tokens, with query pinned only to a uniquely
discovered, regex-valid Synthetic datasource UID and an empty-scope probes read pair. The old SM
token alone causes no scan calls. Legacy-correct roles require zero discovery; absent-query-token
deselection discovers only when a held extra query could match that one Synthetic UID. Other extra
queries stay refused. Reconciliation changes approved pairs without re-minting a working token.

## Scheduled jobs

The reusable module defaults are T1 hourly at :05, T2 daily, T3 six-hourly and T4 daily,
with a daily opt-in provisioner. The timetable below comes from `terraform/variables.tf`;
deployments can override every cron expression and `schedule_timezone` (default `UTC`). Read the
deployment manifest and live EventBridge Scheduler state for its actual schedule, timezone and enabled
state rather than assuming these defaults apply.

| Job | Cadence | Default start times (UTC) | Purpose |
| --- | --- | --- | --- |
| Provisioner | Daily | 03:15 | Reconcile per-stack read-only readers and their credentials; healthy steady state does not mint tokens |
| T1 | Hourly | Five minutes past every hour | Refresh inventory and hourly inputs; hydrate slower inputs and carry their metric series forward |
| T2 | Daily | 03:30 | Gather per-stack identity, plugins, service accounts, usage insights, retention and other daily inputs |
| T3 | Every six hours | 02:40, 08:40, 14:40, 20:40 | Gather data-plane cardinality and Adaptive Metrics recommendations |
| T4 | Daily | 09:00 | Compare completed estate scans over the one-day and seven-day windows |

The four collector schedules default to enabled (`schedules_enabled = true` and each tier's
`enabled = true`). The provisioner is absent unless `create_provisioner = true`; once created,
its schedule needs both `schedules_enabled` and `provisioner_enabled` (default true). Set both
schedule switches false for initial deployment.

These are scheduled start times, not completion times. Runtime depends on the discovered estate,
source pacing and retries. An hourly T1 publication does not make T2 or T3 observations hourly:
check each view's input provenance and age. A manual run is an additional run, not a schedule change.
Deployment-specific timetables belong in the deployment's private operator documentation, not here.

## Manual scans

Local development uses `--dry-run`. A live manual run should use the deployed ECS task definition,
so it receives exactly the scheduled identity and configuration. Include task-definition tag
propagation if cost attribution depends on those tags.

Run a complete refresh serially:

1. T2, which owns most per-stack and Pillar J inputs;
2. T3, which owns cardinality and Adaptive Metrics;
3. T1, which owns inventory and hydrates the other inputs into the fullest view set;
4. T4, which computes the diffs from completed envelopes.

Never include the provisioner in a delegated or concurrent scan batch. It has org-wide service-account
write authority and performs pruning.

Verify a run from both sides:

- the ECS task produced a CloudWatch log stream;
- `scans/<tier>/latest.json` advanced and names the expected input keys;
- input ages on the dashboards are plausible for their owning schedules;
- coverage separates paused/skipped stacks from failures.

Exit `4` is a lock collision, not a failed scan. Do not disable a schedule to work around it.
A limited `--stack` or `--limit` run requires `--dry-run` for diagnostics; without it the scanner
refuses publication.
With it, no S3, Mimir or Loki writes occur.

The query-mix view needs a fresh T2 `insights` input with `query_mix_complete`. Hydrated older inputs
without that marker withhold the new view while keeping the last good copy on S3. A failed optional
query-mix request preserves the core insights input and withholds only this view.

## Provisioner

The provisioner (daily by module default; see [Scheduled jobs](#scheduled-jobs)) reconciles a
basic-role-None service account and `custom:gcinsight.reader` on every provisionable live stack. Healthy steady state is reads with
no token mint. A repair creates a transient Admin identity, records its ids, repairs the role and
assignment, verifies them, and deletes the Admin identity last.

The repair path must not mint when the stored token still works. Token names are organisation-wide
unique, so an unnecessary mint can create a timestamped credential and orphan the original.

After changing the role:

- compare action/scope pairs, not action names;
- allow for partial RBAC propagation before testing the existing token;
- verify `datasources:query` remains uid-scoped: usage-insights everywhere and the usage datasource on
  the nominated write stack only, plus the unique valid SM UID only with both Synthetic tokens;
- where separate test-write authority exists, prove writes remain refused against test endpoints;
  read-only scan authority does not authorise a write probe;
- confirm basic role is still `None` and `chats:access` is absent.

The provisioner CLI reconciles readers; it has no rotation or teardown command. A separately
authorized credential rotation must verify the replacement SSM value before deleting the old token.
Teardown and repair use recorded ids, never a name pattern.

## Dashboards

Create local views from the synthetic fixture:

```bash
python3 bin/make_local_views.py --out /tmp/gcinsight-views
export GCINSIGHT_VIEWS_DIR=/tmp/gcinsight-views
```

For a live build set `GCINSIGHT_WRITE_STACK_URL`, `GCINSIGHT_WRITE_STACK_ID` and
`GCINSIGHT_GRAFANA_TOKEN`. The builder resolves the insights folder by title. The build token is not a
runtime secret. Publish one dashboard or `all`, read it back, and verify the v2 query, viz and link
envelopes.

The builder needs live views to derive Infinity columns. A newly implemented view must be published by
its owning tier before a table panel references it. Legitimately empty finding views use explicit
schemas. A genuinely missing optional product view omits only its table or empty product tab;
a missing required view remains a build failure. Retained older optional views are still read,
with their original timestamp and advancing age. Access, transport and parse failures remain errors,
not a licence to omit a panel.

### Empty or missing views

The S3 writer publishes empty row sets when composition supplies the view. A legitimately empty
finding table uses its declared fallback schema, including idle estate leftovers and dead Fleet
registrations. A measured but all-unscored maturity population still publishes its leaderboard and
explanation when data-plane inputs are available.

A missing object is different: schema fallback does not bypass reading required views. Optional
product views can be genuinely absent before opt-in collection; only their own table/tab is omitted.
Never interpret this as measured zero or ignore an access/parse failure. Check whether the
owning tier ran successfully, whether its required inputs were available and fresh, and whether the
view was withheld. Preserve the last good object rather than fabricating rows. `EmptyView` means an
existing row set is empty without a usable fallback; identify the panel and view and report a missing
schema if empty is legitimate. Do not skip a whole dashboard merely because the estate has no findings.

### Adaptive coverage and product freshness

The Cost rules-read panel measures readable rule input only, not recommendation-count validity or
price completeness. Partial coverage yields explicitly qualified subtotals without an estate gauge;
changing the measured population is not remediation. Current-main segmentation discovery must be
known unsegmented for whole-stack savings/maturity confidence. Segmented, unknown or legacy inputs
suppress default-only confidence; per-segment positive marginal counts do not establish additive
savings. No segment creation/deletion is performed by scans.

Optional product views depend on their own T2 inputs. Withholding leaves older S3 views intact:
inspect observation time and input age rather than equating an hourly hydrated publication with
fresh daily collection. See the [view reference](docs/views.md).

## Rate card

The optional object is `config/ratecard.csv` in the deployment bucket. Absence means volume-only
panels. A deployment may price only some dimensions, but the UI must disclose unpriced components and
must not call a subtotal the total. Mixed currencies, duplicate dimensions, unsupported units and
non-positive prices are configuration errors. Metrics may use `base_rate_only` to exclude DPM or
`dpm_aware` with the contract's `included_dpm` divisor; the latter is evaluated per stack from live
active-series and total-DPM inputs.

## Alerts

Build rules with:

```bash
python3 bin/alerts.py --list
python3 bin/alerts.py --publish
```

New rules publish paused and unrouted. Activate only after every scheduled tier has landed:

```bash
python3 bin/alerts.py --activate --receiver <contact-point-name>
```

Activation refuses an omitted receiver because an unpaused rule without notification settings inherits
the stack's notification policy. A plain publish preserves an existing rule's pause and routing state.
Alert identity is the uid. Use `--migrate-titles --dry-run` before the one-time historical title
migration; it edits the live rule body by uid and preserves routing and pause state.

After publishing, verify every expected uid exists once, is in the intended folder/group, has the
expected health, pause state and receiver, and has no old-title duplicate.

## Optional Firehose logs

The collector writes its own structured Loki records, but it cannot report an image-pull failure,
bootstrap error, early traceback or OOM kill. The optional Firehose path forwards ECS CloudWatch logs
to Loki and is off by default.

Enable it in three stages:

1. set `firehose_logs_enabled=true` with a dedicated adopted secret containing
   `{"api_key":"<loki-tenant>:<logs-write-token>"}`;
2. send a deliberate test record and verify Loki plus failed-record S3;
3. only then set `firehose_log_subscription_enabled=true`.

The subscription switch cannot stand alone. Failed deliveries have their own encrypted, lifecycle-bound
bucket.

Stage 2 is worth doing properly, because it is the only stage that proves the credential. A successful
`put-record` returns a RecordId whatever the credential is; what proves delivery is
`DeliveryToHttpEndpoint.Success` on the stream and an empty failed-record bucket. Allow a few minutes -
these metrics lag the delivery.

### If stage 3 reports that the active stream is unavailable

`PutSubscriptionFilter` fails with:

```
InvalidParameterException: Could not deliver test message to specified Firehose stream.
Check if the given Firehose stream is in ACTIVE state.
```

**The stream can be ACTIVE while the message is still returned.** The error also covers failure to
assume the subscription role. CloudWatch Logs passes the bare log-group ARN as `aws:SourceArn`; the
current module matches that exact ARN and retains the `aws:SourceAccount` condition. A deployment still
matching `<log-group-arn>:*` is on an older module revision or carries trust-policy drift.

Inspect the planned trust policy before retrying. It must contain this deployment's bare log-group ARN,
with no `:*` suffix, and this AWS account. Update the pinned generic revision or repair the drift, then
create the filter against a log group which has never had one. An existing filter is not acceptance
evidence because the condition is evaluated when the filter is created.

## Credential and policy checks

The project owns exactly the access policies explicitly created for its reader, writer and provisioner.
Never update or delete another access policy while operating this platform.

Use IAM policy simulation to prove the Infinity principal is allowed on `views/*` and denied on
`scans/*` and `locks/*`. For `ssm:GetParametersByPath`, test the bare path ARN as well
as a child ARN; the API authorises the path itself.

## Rollback

Local ECR publication uses immutable `sha-<commit>` tags; public release images have release tags.
In either case, roll back to the recorded immutable digest and matching configuration, not a moving
tag. A normal image build does not move `latest`; doing so requires the explicit compatibility flag.

Customer consumers use the stronger contract in `consumer/MIGRATION-RUNBOOK.md`: the deployment
manifest, generic module ref, and registry digest move together, and the image records both repository
revisions plus the overlay digest. Capture current task definitions and schedule targets before applying
that rollback. Source rollback never deletes or overwrites S3 state automatically.

### Hydration schema compatibility and retained-scan recovery

Starting with v0.7.0, each accepted optional scan input records a non-negative integer
`meta.inputs.<input>.schema_version`. Inventory is always freshly discovered, never hydrated.
Version 1 is the explicit versioned envelope contract for every current optional input, including
qualified Adaptive Metrics counts that may be `null`. A consumer accepts versions from 0 through
its supported per-input version. A newer version or an explicitly malformed version is unavailable
**before composition**: dependent views are withheld, their last-good S3 copies survive, and unknown
counts or savings do not become zeros. Version numbers are per input, not per image or whole scan;
a breaking payload change must increment the affected input's version.

Missing version metadata is legacy version 0, not proof that the payload has numeric counts.
Current consumers accept those legacy layouts conservatively: absent/unknown Adaptive counts stay
unknown, and missing segmentation discovery cannot establish whole-stack savings or adoption.
Hydration preserves the producer's version; it does not relabel legacy input as version 1. Existing
source-health and maximum-input-age checks still apply. A version is compatibility metadata, not
proof of availability, complete estate coverage, or freshness.

An upgrade to v0.7.0 can therefore read retained legacy scans, and a version-aware rollback can
withhold input newer than it understands. **Rollback below v0.7.0 requires retained compatible scan
restore as well as the recorded image/configuration rollback.** Older binaries have no version fence;
some try `float(null)` on newer Adaptive payloads. Merely repinning their digest cannot repair S3
state. Do not strip version fields, substitute zeros, or rewrite a scan timestamp to bypass checks.

Before an authorized rollback:

1. Record the current immutable image/configuration and exact S3 object keys/version IDs for
   `scans/<tier>/latest.json`. Retain the pre-upgrade owner scans (especially T3) and their timestamps,
   schema/provenance and coverage records. A timestamped scan or retained S3 version is recovery
   material only while it remains present under the bucket's retention policy.
2. Obtain fresh, successful full estate discovery from the intended organisation. Require exact
   equality of the retained scan's inventory and the live inventory by stack ID and slug, including
   paused status; neither a subset nor matching counts is equality. Compare against `data.stacks`,
   never infer the estate from dataplane payload membership. Missing inventory, additions, removals,
   renamed stacks or status changes block retained restore; obtain a compatible full owner scan
   under separately authorized operating procedures instead.
3. Check that each retained input is compatible with the target binary, passed its independent
   coverage checks, and remains within the normal hydration age cap at recovery time. For an older
   Adaptive consumer that requires numeric counts, inspect every live in-scope stack's required
   `recommendations_pending` and `rules_applied` fields as actual numbers, not `null` or coerced zero.
   Inspect savings/segmentation qualifications too: numeric counts alone do not authorize a
   whole-stack or currency claim. Stop if no compatible, fresh retained scan exists.
4. Under explicit live-change authority, coordinate schedules and in-flight publishers so a newer
   owner cannot overwrite the restoration during rollback. Restore only the selected exact retained
   owner scan(s) to their `scans/<tier>/latest.json` keys, preserving all timestamps and payloads.
   Record the source and restored version IDs and read back to verify exact content. Do not overwrite
   views, delete history, change credentials, or grant product readers as part of recovery.
5. Verify the next complete consumer run from both sides: its task exits successfully and its scan
   advances with the full freshly discovered estate. Inspect input provenance and withheld views,
   unknown counts/savings and the resulting cost views, not exit 0 alone. If the retained scan ages
   out, leave dependent views visibly stale until a compatible owning-tier scan succeeds. A manual
   scan or schedule change still requires its own authority; this procedure grants neither.

Do not publish an image from a dirty tree. The build script refuses a dirty push unless the override is
explicit and reports the uncommitted paths.

## Re-pointing the write target

Changing the write stack changes the Mimir and Loki tenants, Grafana resource namespace, folder,
datasource uids and Infinity credential. Update them together and decide explicitly whether history is
abandoned or migrated. A new target is not a dashboard-only change.

## Teardown

1. Disable schedules first.
2. Deactivate or delete the platform alert rules and dashboards using recorded uids.
3. Perform separately authorized reader cleanup using recorded role, service-account and token ids;
   `bin/provision.py` has no teardown mode. Keep an authorized Admin identity until custom roles
   are removed, then remove the transient Admin identity last.
4. Revoke only this project's three access-policy tokens and delete only its policies.
5. Destroy Terraform-managed AWS resources.
6. Handle adopted resources separately; they are deliberately outside Terraform ownership.

Report any material deletion and whether the source object or state record allows recovery.

## Diagnosing failures

- Empty periodic Prometheus panel: confirm it is a range query with `lastNotNull`.
- T2 or T3 data missing in a six-hour dashboard window: inspect hydration and the owning scan envelope.
- Confident zero from a list endpoint: confirm the role pair before trusting the response.
- Usage-insights values repeated across stacks: inspect the `instance_id` selector immediately.
- Adaptive saving equals all series on unadopted stacks: confirm verbose counts and marginal arithmetic.
- Currency missing: absence is correct when the card or dimension is unpriced; inspect the disclosure.
- Per-stack sweep empty: simulate SSM access on the bare token-prefix ARN.
- Provisioner performs widespread writes on a healthy estate: stop and inspect drift/mint classification.
- T4 movement after a coverage change: compare measured populations before calling it estate movement.
