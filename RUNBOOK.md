# Runbook - estate insights platform

## Before the first scheduled scan

Tell the write-stack owner that this platform adds active series to that one stack. Measure the
footprint with a range query against the write stack itself; the organisation total is not the
denominator. Also confirm that the deploying organisation accepts clear identity data in S3 and Loki.

Do not enable schedules until:

1. the Secrets Manager object contains separate read, write and provisioner token keys;
2. the image is available under the immutable tag referenced by Terraform;
3. the S3 bucket and stack-token SSM path exist with the intended IAM boundaries;
4. one manual run of each scan tier has advanced its envelope;
5. the provisioner has reconciled and verified the stack-local readers;
6. the dashboards and paused alert rules have been published with a short-lived build token.

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
- verify `datasources:query` remains uid-scoped;
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
