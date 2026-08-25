# Runbook - estate insights platform

## Standing up a new deployment

This section is the whole procedure for a named organisation, in the order it must actually happen.
Each phase states what to collect, what to run, and what proves the phase finished. Do not skip
forward: several steps look independent and are not, and phase 6 in particular fails in a way that
reads like a broken credential if phase 5 has not run.

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
  -d '{"name":"gcinsight-build-<date>","secondsToLive":0}' \
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

Apply with `schedules_enabled = false`, `provisioner_enabled = false` and
`firehose_log_subscription_enabled = false`. Everything exists; nothing fires. Doing this out of order
gives four tasks an hour failing to start, and the first symptom is a CloudWatch bill rather than an
error anyone reads.

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
later tiers own; by the end of T1 nothing should be withheld. T4 declining to diff is correct on a
young deployment - it needs two scans in a window before it can compute one.

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

Dashboards need live views, so this cannot precede phase 7. Alert rules publish paused and unrouted;
leave them that way until the schedules have been on long enough for one run of each tier to land, or
the staleness rules are correctly in breach the moment they are activated.

**A small or clean estate can fail this phase.** See *Empty views on a small estate* below - it is a
current product limitation, not a misconfiguration.

Delete the build service account when this phase is done.

### 10. Turn it on, in this order

Firehose log subscription (only after a deliberate test record has been delivered), then the collector
schedules, then the provisioner schedule last - it is the only scheduled job that can write.

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
A limited `--stack` or `--limit` run cannot publish.

## Provisioner

The daily provisioner reconciles a basic-role-None service account and
`custom:gcinsight.reader` on every provisionable live stack. Healthy steady state is reads with
no token mint. A repair creates a transient Admin identity, records its ids, repairs the role and
assignment, verifies them, and deletes the Admin identity last.

The repair path must not mint when the stored token still works. Token names are organisation-wide
unique, so an unnecessary mint can create a timestamped credential and orphan the original.

After changing the role:

- compare action/scope pairs, not action names;
- allow for partial RBAC propagation before testing the existing token;
- verify `datasources:query` remains uid-scoped: usage-insights everywhere and the usage datasource on
  the nominated write stack only;
- prove writes remain refused with harmless write requests against test endpoints;
- confirm basic role is still `None` and `chats:access` is absent.

Rotation is an explicit provisioner operation. Confirm the new SSM value works before deleting the old
token. Teardown and repair use recorded ids, never a name pattern.

## Dashboards

Create local views from the synthetic fixture:

```bash
python3 bin/make_local_views.py
export GCINSIGHT_VIEWS_DIR=testdata/views
```

For a live build set `GCINSIGHT_WRITE_STACK_URL`, `GCINSIGHT_WRITE_STACK_ID` and
`GCINSIGHT_GRAFANA_TOKEN`. The builder resolves the insights folder by title. The build token is not a
runtime secret. Publish one dashboard or `all`, read it back, and verify the v2 query, viz and link
envelopes.

The builder needs live views to derive Infinity columns. A newly implemented view must be published by
its owning tier before a table panel references it. Legitimately empty finding views use explicit
schemas; a never-published view remains a build failure.

### Empty views on a small estate

That last sentence describes the intent. The implementation does not currently hold it up, and a small
or clean estate is where it shows.

A view with zero rows is not written to S3 at all, and `build.columns_for` raises `EmptyView` when it
cannot derive an Infinity column spec - Infinity's backend parser returns HTTP 500 for the whole panel
on an empty `columns`, so refusing is correct. The fallback exists as each pillar's `VIEW_SCHEMAS`, but
it has to be threaded through by hand at every call site, and not every call site does it.

The result on a small estate is `--publish all` dying, in two shapes that are one cause:

- a call site with no `schema=` raises `EmptyView` - `estate` on `estate_leftovers_idle` and `risk` on
  `risk_fleet_dead`, while `estate_leftovers_billing` on the adjacent line passes its schema and is
  fine;
- a view that was never written 404s on read - `maturity`, whose leaderboard was empty.

So "correctly empty" and "never wired up" are **not** currently distinguishable, which is the exact
distinction the design intends. The reason it shipped is that `testdata/` holds a full synthetic estate,
so no test has ever exercised a zero-row view.

Nothing in a deployment can work around it: the schema has to travel from the pillar, so the fix is in
the product. Until then, the affected dashboards are skipped and the rest publish normally.

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

### A new deployment currently cannot complete stage 3

`PutSubscriptionFilter` fails with:

```
InvalidParameterException: Could not deliver test message to specified Firehose stream.
Check if the given Firehose stream is in ACTIVE state.
```

**The stream is ACTIVE and the message is misleading.** The real failure is the AssumeRole behind that
test message. CloudWatch Logs assumes the subscription role passing the **bare log-group ARN** as
`aws:SourceArn`, while the module's trust policy matches `<log-group-arn>:*`, so the condition never
matches. Isolated against a throwaway role: `aws:SourceAccount` alone works, `ArnLike` on
`<log-group-arn>:*` is blocked, and the identical condition without the `:*` suffix works.

An existing subscription filter keeps working, because the condition is evaluated only when the filter
is created. This therefore looks like it affects nobody until someone stands up a new deployment - and
it affects every one of them. Leave `firehose_log_subscription_enabled` false until the module's trust
policy is fixed; ECS task logs remain in CloudWatch meanwhile, and only the copy to Loki is missing.

## Credential and policy checks

The project owns exactly the access policies explicitly created for its reader, writer and provisioner.
Never update or delete another access policy while operating this platform.

Use IAM policy simulation to prove the Infinity principal is allowed on `views/*` and denied on
`scans/*` and `locks/*`. For `ssm:GetParametersByPath`, test the bare path ARN as well
as a child ARN; the API authorises the path itself.

## Rollback

Images are published under immutable `sha-<commit>` tags. Roll back by restoring the previous
Terraform image value and applying. A normal image build does not move `latest`; doing so requires
the explicit compatibility flag.

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
3. Run the provisioner teardown against recorded role, service-account and token ids.
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
