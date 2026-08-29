# Deployment

`terraform/` is a reusable module with no provider block. `terraform/examples/standalone/` is the copy-and-edit root. It works on OpenTofu and Terraform, and needs the AWS provider v6.

The module provisions the platform. It does **not** provision the Grafana dashboards - those are published separately by `bin/dashboards.py`, described in [Dashboards and alerts](dashboards.md).

## What it creates

| | |
|---|---|
| S3 bucket | `scans/` (raw, expiring), `views/` (dashboard tables, permanent), `locks/` (single-run locks) |
| ECS | Fargate cluster, one task definition per tier, CloudWatch log group |
| EventBridge Scheduler | one schedule per enabled tier |
| IAM | execution role, task role, scheduler role, and a `views/`-only reader for the Grafana datasource |
| Secrets Manager | the container for the Grafana Cloud tokens - **values are never managed here** |
| ECR | optional repository for the collector image |
| Data Firehose | optional, default-off ECS-log delivery to the same Loki target, with failed-record S3 backup |

## Why the credentials are split

The collector wants two tokens, and the split is the security property rather than tidiness.

- **Reader** - org realm, read-only scopes, reaches every stack in the org.
- **Writer** - *stack* realm covering the one publishing target, with `metrics:write` and `logs:write`.

The writer cannot touch any other stack because the realm forbids it, not because a scope check says so. A single combined credential able to both scan the estate and write to it would be strictly more dangerous than the pair.

Both live as JSON keys in one Secrets Manager secret and are injected by the ECS agent, so they never appear in Terraform state, a plan diff, or the task role's permissions.

## First deployment, in order

Doing these out of order gives four tasks an hour failing to start, and the first symptom is a CloudWatch bill rather than an error anyone reads.

1. `terraform apply` with `schedules_enabled = false` and `provisioner_enabled = false`. Everything exists; nothing fires.
2. Write the tokens into the secret. The shape is in `secrets.tf`.
3. Build and push the image. **It must match `task_architecture`** - the default is ARM64, and an x86 image on an ARM64 task definition fails at runtime with `exec format error`, not at plan time. Pin the pushed digest and apply again.
4. **Run the provisioner by hand, before any scan tier.** It writes one per-stack reader token to SSM, and T2 cannot pass without them: every stack-local source returns `no_credential`, coverage is `0.0`, and the tier exits `1` refusing all writes. That failure reads like a broken reader token and is not one.
5. Run the tiers by hand (`terraform output run_task_command`), serially, T2 → T3 → T1 → T4, and read their logs.
6. Mint the access key for the views reader and wire the Grafana Infinity datasource to it.
7. Publish the dashboards, then the alert rules, which publish paused.
8. Set `schedules_enabled = true`, and enable the provisioner schedule last - it is the only scheduled job that can write.

The full procedure for a named organisation - which credentials to create in which region, the folder that must exist before a dashboard build, and what proves each phase finished - is *Standing up a new deployment* in the runbook. [Running scans](operations.md) lists what else must be true before the first scheduled scan.

## Building the image

```bash
bin/build-and-push.sh --repo <ecr-uri> --no-push   # ARM64, no Python dependencies
bin/build-and-push.sh --repo <ecr-uri>             # push immutable :sha-<commit>
```

Fargate pulls at task start, so a pushed image is picked up by the next scheduled run with no apply.

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

Images are published under immutable `sha-<commit>` tags. Roll back by restoring the previous Terraform image value and applying.

Customer consumers use the stronger contract in `consumer/MIGRATION-RUNBOOK.md`: the deployment manifest, generic module ref and registry digest move together, and the image records both repository revisions plus the overlay digest. Capture current task definitions and schedule targets before applying that rollback.

Source rollback never deletes or overwrites S3 state automatically.

## Re-pointing the write target

Changing the write stack changes the Mimir and Loki tenants, the Grafana resource namespace, the folder, the datasource uids and the Infinity credential. Update them together, and decide explicitly whether history is abandoned or migrated.

A new target is not a dashboard-only change.

## Teardown

1. Disable schedules first.
2. Deactivate or delete the platform alert rules and dashboards using recorded uids.
3. Run the provisioner teardown against recorded role, service-account and token ids.
4. Revoke only this project's three access-policy tokens, and delete only its policies.
5. Destroy Terraform-managed AWS resources.
6. Handle adopted resources separately - they are deliberately outside Terraform ownership.

Teardown and repair use recorded ids, never a name pattern. Report any material deletion and whether the source object or state record allows recovery.
