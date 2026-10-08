# Consumer upgrade, deployment, and rollback

This runbook stops at the live-change approval gate. A registry push, task-definition registration,
schedule change, Terraform apply, live scan, provisioner run, dashboard publish, or alert publish needs
separate authorization.

## Immutable upgrade

Choose a reviewed full generic commit, fetch it locally, and update the deployment-owned manifest and
Terraform ref together:

```bash
python3 bin/consumer_manifest.py upgrade <40-character-generic-sha> \
  --manifest /path/to/deployment/consumer.json \
  --terraform /path/to/deployment/consumer.tf \
  --generic-source /path/to/grafana-cloud-org-insights
```

Check out the selected commit in a clean generic worktree, then prove the one-way relationship:

```bash
python3 bin/consumer_manifest.py check \
  --manifest /path/to/deployment/consumer.json \
  --generic-source /path/to/grafana-cloud-org-insights \
  --deployment-root /path/to/deployment \
  --terraform /path/to/deployment/consumer.tf \
  --forbidden-core-path modules/retired-insights-module
```

Repeat `--forbidden-core-path` for every historical deployment-owned core location. Set the private
`GCINSIGHT_CUSTOMER_IDENTIFIER_PATTERN` value before running the check; CI stores it as a repository
secret because publishing the pattern set would itself disclose customer context. The check rejects
standard collector, scan, dashboard, and alert core paths in the deployment root.

Run the complete product suite, customer-identifier and shipped-text gates from CI, isolated OpenTofu
validation for the module and standalone example, and deployment-root validation and planning. Compare
the generated metric catalogue, views, dashboard inventory, alert inventory, permission pairs,
schedules, rate-card semantics, hydration ownership, and limited-publication guards with the deployed
baseline. Explain every difference.

Commit the deployment manifest and Terraform wiring. Build and attest a local image only after that
commit exists:

```bash
just consumer-build \
  /path/to/deployment/consumer.json \
  /path/to/deployment \
  /path/to/deployment/consumer.tf \
  --tag local/gcinsight-consumer:validation
```

The build requires a clean generic checkout and committed deployment manifest/wiring. It records the
generic revision, deployment revision, and overlay digest, verifies every runtime projection inside the
image, and never logs in, pushes, or moves a tag.

Both the build and `check --terraform` also compare the manifest with the consumer's module block. In
manifest mode (`consumer_manifest = jsondecode(file("${path.module}/<manifest>"))`, v0.10.0 and later)
the check refuses any explicit argument for an input the manifest represents and any tier
`schedule_expression`, and requires the `consumer_manifest` argument to read the manifest being
checked. With explicit wiring, any runtime key the module renders from a variable must be wired from
the manifest, unless the manifest value equals the module default. Either way a problem names the key
or input, never its value, and stops the build before any push. JSON-valued keys are hashed in Terraform's `jsonencode` form (sorted keys, compact, integral
numbers), so the key order a person typed no longer changes the digest.

On the first upgrade to a revision with that normalisation, an existing manifest's recorded digests no
longer validate, and `upgrade` refuses it. Add any newly required runtime keys, run `regenerate` from
a clean checkout of the TARGET revision, then run `upgrade`.

The upgrade command journals the original and target manifest/Terraform pair before replacing either
file. A check refuses an incomplete journal. Re-running the upgrade restores the original pair from a
valid journal before retrying; it refuses recovery if either file was independently edited.

## Moving to manifest mode (v0.10.0)

1. Upgrade to the v0.10.0 commit as above. The unchanged manifest validates with its old digests.
2. Replace the module block's glue with `consumer_manifest`. Keep only the two kill switches
   (`schedules_enabled`, `provisioner_enabled`, ANDed with the manifest), and the inputs the manifest
   does not represent: `image`, `subnet_ids`, `firehose_access_key_secret_arn`, `tiers` sizing without
   `schedule_expression`, `tags`, `tag_adopted_secret` and `bucket_policy_source_json`. Drop the
   deployment's own merge of the Purpose and Namespace tags: the module applies `aws.purpose_tag` and
   `aws.cost_namespace` over `tags`, so the manifest wins a key clash as the old merge did. Any other gate the
   deployment ANDed into a represented input has no argument left; set the manifest value instead.
   `aws.manage_adopted_bucket_config` (optional, absent means false) is the manifest key for that input.
   The block shape is in
   [terraform/README.md](../terraform/README.md#manifest-mode-for-consumer-deployments).
3. Optionally prune: `python3 bin/consumer_manifest.py regenerate --manifest <m> --prune-defaults`
   from the clean v0.10.0 checkout. Every projection and overlay digest is unchanged, so an image built
   for the unpruned manifest still matches. Keys without a module default, and the names of an adopted
   bucket or secret, always stay.
4. Run the check above, then plan. The plan must show no task-definition, schedule, bucket, secret or
   tag change; the module's `task_environments`, `schedules` and `tags` outputs give the rendered
   values when a difference needs explaining.

A later `upgrade` of a pruned manifest compares the module defaults of the current and target
revisions. It prints the name (never the value) of every omitted key whose effective value would change
and refuses unless `--accept-default-changes` is passed; restore such a key explicitly to keep its old
value instead.

A pruned manifest is valid only for a module revision with manifest mode. Rolling back below v0.10.0
restores the saved unpruned manifest with its old module ref and image digest.

## Deployment stopping conditions

Before requesting go-live authorization, record the current image digest, task-definition revisions,
schedule states and targets, task-definition tag propagation, and the exact deployment revision. Protect
both rollback and candidate image digests from registry lifecycle expiry for the agreed rollback window.

Save a refreshed Terraform plan for the exact committed inputs. Stop on an unclassified action, resource
replacement outside task definitions, adopted-resource mutation, permission widening, credential or
secret-selector change, schedule/default change, identity drift, missing rollback digest, or output
difference without an owner and explanation.

Use the deployment root's approved saved-plan workflow. With the selected Terraform-compatible
engine, the underlying flow is:

```bash
terraform -chdir=/path/to/deployment plan -out=/path/to/private/candidate.tfplan
# Stop here for explicit live-change approval and review of this exact saved plan.
terraform -chdir=/path/to/deployment apply /path/to/private/candidate.tfplan
```

Use `tofu` instead of `terraform` when that is the deployment's selected engine. The plan can contain
sensitive data; keep it private. Apply only the reviewed plan for the exact committed inputs, not a
fresh implicit plan. Deployment wrappers named `plan-out` or `apply-plan-auto` are not product
recipes: inspect their local help and approval contract; an automatic apply is still a live change.

For build-time tooling, supply the manifest, deployment root, Terraform file, projection kind and
command explicitly:

```bash
just consumer-exec /path/to/deployment/consumer.json /path/to/deployment \
  /path/to/deployment/consumer.tf dashboards python3 bin/dashboards.py \
  --out /tmp/dashboards --ds-uid <infinity-datasource-uid>
```

Local dashboard output also needs local views (`GCINSIGHT_VIEWS_DIR`). `consumer-exec` validates
configuration, not authority: a supplied publish or provisioning command can write to live systems.

Deploy collectors with the provisioner independently disabled. Inspect the rendered task definitions and
runtime digests before any run. Run tiers serially in dependency order using deployed task definitions,
verifying both a log stream and the advanced scan envelope. For a new deployment, reconcile
stack-local readers with separate authorization before T2; otherwise its stack-local sources cannot
publish. Enable the provisioner schedule last, after its no-write
steady-state result is understood. Module defaults and timezone are in the
[runbook timetable](../RUNBOOK.md#scheduled-jobs); deployment overrides need separate comparison.

## Rollback

Rollback restores the recorded deployment commit, generic module ref, immutable image digest,
task-definition targets, schedule states, and provisioner gate. Re-run the rendered-definition and
schedule checks after apply.

Keep the original manifest, Terraform module ref and immutable image digest as a saved rollback
triplet. The current `consumer_manifest.py upgrade` statically inspects the requested commit's
projection names before writing and rejects a different or unsupported schema. It does not execute
target code or convert manifests across arbitrary versions. For an incompatible target, use
target-matched tooling or restore that saved triplet; never blindly run a newer `regenerate` on the
saved rollback manifest. The guard does not replace the recorded rollback procedure or prove target
runtime behavior. Supported forward legacy migration still verifies old digests before carrying the
existing provisioner product policy into the scanner projection.

Rollback does not automatically delete or overwrite scan, carry, or view objects. If a candidate wrote
bad state, preserve it as evidence and assess data recovery separately from source rollback.
