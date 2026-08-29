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
bin/consumer-build \
  --manifest /path/to/deployment/consumer.json \
  --deployment-root /path/to/deployment \
  --terraform /path/to/deployment/consumer.tf \
  --tag local/gcinsight-consumer:validation
```

The build requires a clean generic checkout and committed deployment manifest/wiring. It records the
generic revision, deployment revision, and overlay digest, verifies every runtime projection inside the
image, and never logs in, pushes, or moves a tag.

The upgrade command journals the original and target manifest/Terraform pair before replacing either
file. A check refuses an incomplete journal. Re-running the upgrade restores the original pair from a
valid journal before retrying; it refuses recovery if either file was independently edited.

## Deployment stopping conditions

Before requesting go-live authorization, record the current image digest, task-definition revisions,
schedule states and targets, task-definition tag propagation, and the exact deployment revision. Protect
both rollback and candidate image digests from registry lifecycle expiry for the agreed rollback window.

Save a refreshed Terraform plan for the exact committed inputs. Stop on an unclassified action, resource
replacement outside task definitions, adopted-resource mutation, permission widening, credential or
secret-selector change, schedule/default change, identity drift, missing rollback digest, or output
difference without an owner and explanation.

Deploy collectors with the provisioner independently disabled. Inspect the rendered task definitions and
runtime digests before any run. Run tiers serially in dependency order using deployed task definitions,
verifying both a log stream and the advanced scan envelope. Enable the write-capable provisioner last,
after its no-write result is understood.

## Rollback

Rollback restores the recorded deployment commit, generic module ref, immutable image digest,
task-definition targets, schedule states, and provisioner gate. Re-run the rendered-definition and
schedule checks after apply.

Rollback does not automatically delete or overwrite scan, carry, or view objects. If a candidate wrote
bad state, preserve it as evidence and assess data recovery separately from source rollback.
