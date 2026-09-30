# Clean-room validation before a first deployment

This procedure stops before live-change approval. It does not authorize a registry push, Terraform
apply, credential creation, task run, provisioner run, schedule change, dashboard publish or alert
publish. A local build or a successful validation is not proof that AWS or Grafana will accept a
new deployment.

## Prerequisites and repository boundary

Use Git, Python 3.14 with venv support (the repository's CI and container version), `just`, OpenTofu
>= 1.6 and a running Docker daemon with BuildKit and support for the chosen task architecture.
Before setup and consumer commands, run `python3 --version` and `command -v python3`; make sure
`python3` on PATH resolves to the intended interpreter. The clean-room validation exercised Python
3.14.7; an earlier documentation-only gate also passed on 3.13.15, which is not a lower-version
support guarantee. `just setup` installs the pinned test runner; OpenTofu init downloads the AWS v6 provider. Those downloads and a Docker base-image pull require network
access even though the product tests require neither AWS nor Grafana credentials.

You need two repositories: the public product and a deployment-owned repository. The latter may be
private. Its URL, access grant, backend, lock file and deployment values belong to its owner; there
is no universal private repository to clone. For a synthetic rehearsal, create an empty local Git
repository, make an initial commit, then clone it as the deployment repository. This does not prove
access to the eventual private repository.

Place both clones and all evidence outside the product tree, especially outside directories scanned
by tests and shipped-text checks. Do not reuse an engagement workspace, installed provider cache or
existing Terraform state as evidence of a first installation.

```bash
mkdir -p /path/to/clean-room
cd /path/to/clean-room
git clone https://github.com/rknightion/grafana-cloud-org-insights.git product
git clone <deployment-repository-url> deployment
cd product
git checkout --detach <reviewed-full-product-commit>
git rev-parse HEAD
python3 --version
command -v python3
just setup
```

Keep the same supported `python3` first on PATH when invoking `just`: its setup and consumer wrappers
resolve `python3` from PATH, not from the test venv. Creating `.venv` alone does not switch those
wrappers to its interpreter. Do not reuse a venv created by another interpreter as parity evidence.

Record both full Git revisions. Confirm that `.terraform` directories and `terraform.tfstate` are
absent in each Terraform root before initialization. Do not delete an existing state or cache to
make a reused checkout look fresh. Start another clone instead.

## Identifier gate without disclosing its pattern

`GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN` is a private identifier pattern, not a product default. The
public repository stores it only as a CI secret. Do not try to retrieve that secret, print the
inherited environment, copy it into a manifest, or invent a permissive substitute to obtain green
validation. The check fails closed when no pattern is supplied.

An authorized operator needs an approved private delivery path from the pattern owner. The owner
can inject the variable into the validation process without displaying it; alternatively the
standalone identifier gate accepts an owner-provided private patterns file:

```bash
just check-identifiers --patterns-file /absolute/private/path/to/approved-patterns
```

The consumer manifest checker and consumer build require the environment variable; the file option
on `check-identifiers` does not configure those commands. Do not put a secret value on a command
line or in shell history. If the authorized process has not received the pattern, stop and record
identifier validation as blocked, not clean. Running the CI gate with its configured secret is the
normal independent verification path. In a bounded lane, use only the already-authorized injected
process, not credential discovery.

## First consumer manifest and candidate

A first deployment has no manifest for `upgrade` to update. Create `deployment/consumer.json` using
[`consumer/manifest.schema.json`](../consumer/manifest.schema.json). Include every required `aws` and
`policy` field and all four `runtime` projections. The projection key contract is
`PROJECTION_ENVS` in `collector/identity.py`; runtime meanings are described in
[Configuration](configuration.md). These are non-secret values, not credentials. Keep reader product
policy identical in scan and provisioner. Include explicit privacy acceptance rather than assuming
bounded metric labels permit clear identity storage.

Set `generic_source.repository` to the public product URL and `generic_source.revision` to the full
checked-out commit. For initial construction only, use 64 zeroes as placeholders for `overlay_digest`
and the four `runtime_projection_digests`, then calculate them with the selected product tooling:

```bash
python3 bin/consumer_manifest.py regenerate \
  --manifest /path/to/clean-room/deployment/consumer.json
```

Regeneration calculates digests; it does not prove the deployment root, module wiring or identifier
gate. Create deployment-owned Terraform wiring with a module ref pinned to that same full commit,
and wire non-default runtime values from the manifest. The standalone example is an infrastructure
starting point, not a complete consumer-manifest adapter: copying it alone does not prove this seam.
Follow [Consumer upgrade, deployment, and rollback](../consumer/MIGRATION-RUNBOOK.md) for the full
`check` command, including historical retired-core paths when any exist. Do not copy product core
into the deployment repository.

Commit the manifest and Terraform wiring in the deployment repository before `just consumer-build`.
Keep the product checkout clean. Save the build's verified provenance, image content identity and
both Git revisions. A local Docker tag is only a handle, not the future registry manifest digest.
The consumer build defaults to `linux/arm64`. For an X86_64 deployment, pass
`--platform linux/amd64` explicitly to `just consumer-build` and inspect the resulting image's
architecture against `task_architecture`; a host architecture is not evidence of image parity.
The consumer build never pushes. A successful generic `just image --repo local/gcinsight-validation`
is useful build evidence but is not a substitute for manifest validation and the consumer build.

## Isolated infrastructure validation and planning

From the fresh product checkout, with no configured backend or reused state:

```bash
just tf-validate
```

This initializes and validates both `terraform/` and `terraform/examples/standalone/`, then checks
formatting. The module has no provider block. The standalone root owns its provider and backend;
its backend block is commented out. Backend-free init does not prove access, locking, encryption
or readiness of a deployment's remote backend; validate those separately before live approval.
If copying that root elsewhere, change the relative module
source to an explicit reviewed source before init.

`init -backend=false` and `validate` do not prove an AWS plan. The module reads AWS caller identity,
region, partition and the first subnet, and can read an adopted secret's metadata. A real plan
therefore needs an authorized AWS identity and real deployment network values. An empty state and
`-refresh=false` do not suppress initial data-source reads. Do not run a plan under an ambient AWS
profile and call it an offline synthetic plan. Do not invent account or subnet results and describe
them as a validated deployment.

For an owner-authorized read-only candidate plan, keep both collector and provisioner schedules
disabled and Firehose subscription disabled. Save the plan in a private evidence directory:

```bash
tofu -chdir=/path/to/deployment/root init -backend=false
tofu -chdir=/path/to/deployment/root validate
tofu -chdir=/path/to/deployment/root plan -input=false -out=/private/evidence/candidate.tfplan
tofu -chdir=/path/to/deployment/root show -no-color /private/evidence/candidate.tfplan
```

Do not apply. Review the exact inputs and actions against the stopping conditions in the consumer
runbook. Plans can contain deployment identifiers and sensitive metadata: keep them out of the
public product repository and shared review services. The standalone example exposes `image` and `provisioner_enabled`, with an empty image fallback
for initial infrastructure and a safe-off provisioner default. Set a reviewed registry digest before
runtime approval. The module defaults `create_provisioner` to false; the standalone example leaves
that creation choice unchanged. `provisioner_enabled` only gates its schedule, not task creation.
A full deployment-owned root must explicitly select creation with approval, or establish an approved
external provisioning path before T2. The example is still not a complete consumer-manifest adapter:
a deployment-owned root must wire its runtime projections before consumer validation. Its generated `next_steps` text is
not authorization to run live operations.

If no AWS reads or credentials are authorized, stop after validation and return the plan as
**unproven**. An offline schema rehearsal is a separate proof, not a live candidate plan.

## Rollback package and final gate

For an existing deployment save the original manifest, module ref, immutable registry image digest,
deployment revision, task-definition revisions, schedule targets and states, and provisioner gate.
Record registry retention for both image digests. A new synthetic repository has no deployed baseline;
record that explicitly rather than manufacturing a rollback digest. Infrastructure teardown is a
separate destructive operation, not first-deployment source rollback.

Run `just check` on the exact final product candidate. Retain the exit status and tested full commit
or patch identity. Review local build provenance and the saved candidate plan separately. List any
unproven private-repository access, credential grants, registry pull access, image architecture,
backend policy, adopted-resource controls and live runtime assumptions before requesting approval.
