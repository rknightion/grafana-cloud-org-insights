# Runbook - estate insights platform

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
