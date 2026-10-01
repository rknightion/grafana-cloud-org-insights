# Deployment

`terraform/` is a reusable module with no provider block. `terraform/examples/standalone/` is the copy-and-edit root. It works on OpenTofu and Terraform, and needs the AWS provider v6.

The module provisions the platform. It does **not** provision the Grafana dashboards - those are published separately by `bin/dashboards.py`, described in [Dashboards and alerts](dashboards.md).

## What it creates

| | |
|---|---|
| S3 bucket | `scans/` (raw, expiring), `views/` (last-good dashboard tables; raw label-risk view expires), `locks/` (single-run locks) |
| ECS | Fargate cluster, one task definition per tier, CloudWatch log group |
| EventBridge Scheduler | one schedule per configured tier, with enabled state controlled separately; optional provisioner schedule |
| IAM | execution role, task role, scheduler role, and a `views/`-only reader for the Grafana datasource |
| Secrets Manager | the container for the Grafana Cloud tokens - **values are never managed here** |
| ECR | optional repository for the collector image |
| Data Firehose | optional, default-off ECS-log delivery to the same Loki target, with failed-record S3 backup |

For module-created buckets, `scan_retention_days` (default 90) covers current `scans/` objects and
the reserved full-key prefix `views/risk_label_hygiene.json`, measured from last publication (including
hydrated republication). Noncurrent versions expire after seven days; AWS processing is asynchronous,
not strict erasure 90 days after observation. Other last-good views do not expire. Adopted buckets
need equivalent targeted lifecycle rules in their existing configuration before raw-match publication,
plus verified versioning, encryption, reader access and an effective non-TLS deny policy. Do not add a
competing lifecycle configuration or expire all views.

## Why the credentials are split

The collector wants two tokens, and the split is the security property rather than tidiness.

- **Reader** - org realm, read-only scopes, reaches every stack in the org.
- **Writer** - *stack* realm covering the one publishing target, with `metrics:write` and `logs:write`.

The writer cannot touch any other stack because the realm forbids it, not because a scope check says so. A single combined credential able to both scan the estate and write to it would be strictly more dangerous than the pair.

Both live as JSON keys in one Secrets Manager secret and are injected by the ECS agent, so they never appear in Terraform state, a plan diff, or the task role's permissions.

## First deployment, in order

First complete [Clean-room validation](clean-room-validation.md). That rehearsal stops before live
change and documents the private identifier-pattern prerequisite, first manifest construction,
local-build provenance, AWS plan assumptions and rollback evidence. The steps below require separate
live-change approval.

Doing these out of order starts tasks before their image and credentials are ready. Failure frequency
follows the configured schedules. See the [runbook timetable](../RUNBOOK.md#scheduled-jobs): module
defaults are T1 hourly at :05, T2 daily, T3 six-hourly, T4 daily and a daily opt-in provisioner, all in
UTC by default. Deployment cron and timezone overrides must be checked separately.

1. Opt in to stack-local reader provisioning with `create_provisioner = true` (default false).
   Apply the approved saved plan with `schedules_enabled = false`, `provisioner_enabled = false`
   and `firehose_log_subscription_enabled = false`. Infrastructure exists; no schedule fires.
2. Write the tokens into the secret. The shape is in `secrets.tf`.
3. Build and push the image. **It must match `task_architecture`** - the default is ARM64, and an x86 image on an ARM64 task definition fails at runtime with `exec format error`, not at plan time. Pin the pushed digest and apply again.
4. **Run the provisioner by hand, before any scan tier.** It writes one per-stack reader token to SSM, and T2 cannot pass without them: every stack-local source returns `no_credential`, coverage is `0.0`, and the tier exits `1` refusing all writes. That failure reads like a broken reader token and is not one.
5. Run the tiers serially, T2 → T3 → T1 → T4, and verify logs plus advanced scan envelopes.
   The module's `run_task_command` output is a template: fill in the task definition and use the
   recorded revision from `task_definition_arns` for an exact candidate run. A consumer root must
   expose the module output explicitly; `terraform output` reads only root outputs.
6. Mint the access key for the views reader and wire the Grafana Infinity datasource to it.
7. Publish the dashboards, then the alert rules. New rules publish paused and unrouted; ordinary
   publication preserves existing pause and routing state. Verify live state after publication.
   Activation needs separate authority and an explicit receiver.
8. Set `schedules_enabled = true`, and enable the provisioner schedule last - it is the only scheduled job that can write to Grafana's control plane. Collectors write S3, Mimir and Loki.

The full procedure for a named organisation - which credentials to create in which region, the folder that must exist before a dashboard build, and what proves each phase finished - is *Standing up a new deployment* in the runbook. [Running scans](operations.md) lists what else must be true before the first scheduled scan.

## Building the image

```bash
just image --repo <ecr-uri>   # ARM64, no Python dependencies
just publish-image --repo <ecr-uri> # confirm, then push immutable :sha-<commit>
```

Fargate pulls at task start, but an immutable task-definition digest does not change when an image
is pushed. Update the deployment's reviewed image digest and task definition before the next run;
a push alone changes neither the pinned consumer nor its rollback baseline.

The build script refuses a dirty push unless the override is explicit, and reports the uncommitted paths. A normal build does not move `latest`; doing so requires the explicit compatibility flag.

## The public container image

Release and edge images are published to `ghcr.io/rknightion/grafana-cloud-org-insights` for both `linux/amd64` and `linux/arm64`. Release tags are signed with Sigstore keyless signing and carry GitHub build provenance plus SPDX and CycloneDX SBOMs.

A deployment must resolve a reviewed tag to its immutable manifest digest and pin the digest:

```hcl
image = "ghcr.io/rknightion/grafana-cloud-org-insights@sha256:<reviewed-manifest-digest>"
```

The normal deployment pulls the public GHCR image anonymously and directly, where its task subnets have outbound registry access.

Amazon ECR pull-through cache is an optional customer policy choice, and it has one non-obvious requirement: ECR supports GHCR as an upstream, but AWS requires an upstream credential in a same-account, same-region Secrets Manager secret for that cache rule **even when the source package is public**. Its name must begin with `ecr-pullthroughcache/`, and its value carries the GHCR username and personal access token. The generic product does not create or own that credential.

Whether the chosen reference is direct or ECR-cached, the task definition pins the reviewed manifest digest. Neither a moving tag nor a Git push changes an existing task definition.

## Customer deployments

For a customer deployment, use the immutable consumer contract in `consumer/`.

The deployment repository owns the manifest and customer values. This repository owns the schema, validation, build, execution, upgrade tooling and the Terraform module. `consumer/ARCHITECTURE.md` explains the boundary; `consumer/MIGRATION-RUNBOOK.md` gives the exact upgrade, provenance, deployment gate and rollback flow.

Customer consumers pin both the module commit and the image digest, so changing a candidate requires a reviewed deployment change. It is not picked up merely because a tag moved.

## Rollback

Local ECR publication uses immutable `sha-<commit>` tags; public images also have release tags.
Roll back to the saved immutable image digest and matching configuration, not a moving tag.

Customer consumers use the stronger contract in `consumer/MIGRATION-RUNBOOK.md`: the deployment manifest, generic module ref and registry digest move together, and the image records both repository revisions plus the overlay digest. Capture current task definitions and schedule targets before applying that rollback. Restore the saved
manifest, module ref and digest triplet; never regenerate an old manifest with new tooling. Preserve
both candidate and rollback digests against registry expiry for the agreed rollback window.

Source rollback never deletes or overwrites S3 state automatically.

## Re-pointing the write target

Changing the write stack changes the Mimir and Loki tenants, the Grafana resource namespace, the folder, the datasource uids and the Infinity credential. Update them together, and decide explicitly whether history is abandoned or migrated.

A new target is not a dashboard-only change.

## Teardown

1. Disable schedules first.
2. Deactivate or delete the platform alert rules and dashboards using recorded uids.
3. Perform separately authorized reader cleanup using recorded role, service-account and token ids.
   `bin/provision.py` has no teardown mode; retain authorized Admin access until custom roles are
   removed and delete the transient Admin identity last.
4. Revoke only this project's three access-policy tokens, and delete only its policies.
5. Destroy Terraform-managed AWS resources.
6. Handle adopted resources separately - they are deliberately outside Terraform ownership.

Teardown and repair use recorded ids, never a name pattern. Report any material deletion and whether the source object or state record allows recovery.
