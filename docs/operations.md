# Running scans

## Before the first scheduled scan

Tell the write-stack owner that this platform adds active series to that one stack. Measure the footprint with a range query against the write stack itself; the organisation total is not the denominator. Also confirm that the deploying organisation accepts clear identity data in S3 and Loki.

Do not enable schedules until:

1. the Secrets Manager object contains separate read, write and provisioner token keys;
2. the image is available under the immutable tag referenced by Terraform;
3. the S3 bucket and stack-token SSM path exist with the intended IAM boundaries;
4. one manual run of each scan tier has advanced its envelope;
5. the provisioner has reconciled and verified the stack-local readers;
6. the dashboards and paused alert rules have been published with a short-lived build token.

## Manual scans

Local development uses `--dry-run`. A live manual run should use the deployed ECS task definition, so it receives exactly the scheduled identity and configuration. Include task-definition tag propagation if cost attribution depends on those tags.

Run a complete refresh serially, in this order:

1. **T2**, which owns most per-stack and Pillar J inputs;
2. **T3**, which owns cardinality and Adaptive Metrics;
3. **T1**, which owns inventory and hydrates the other inputs into the fullest view set;
4. **T4**, which computes the diffs from completed envelopes.

Never include the provisioner in a delegated or concurrent scan batch. It has org-wide service-account write authority and performs pruning.

Verify a run from both sides:

- the ECS task produced a CloudWatch log stream;
- `scans/<tier>/latest.json` advanced and names the expected input keys;
- input ages on the dashboards are plausible for their owning schedules;
- coverage separates paused and skipped stacks from failures.

Exit `4` is a lock collision, not a failed scan. Do not disable a schedule to work around it. A limited `--stack` or `--limit` run cannot publish.

## The provisioner

The daily provisioner reconciles a basic-role-`None` service account and the `custom:gcinsight.reader` role on every provisionable live stack. Drift is compared as action/scope pairs, not action names.

**Healthy steady state is reads with no token mint.** A repair creates a transient Admin identity, records its ids, repairs the role and assignment, verifies them, and deletes the Admin identity last.

The repair path must not mint when the stored token still works. Token names are organisation-wide unique, so an unnecessary mint can create a timestamped credential and orphan the original.

After changing the role:

- compare action/scope pairs, not action names;
- allow for partial RBAC propagation before testing the existing token;
- verify `datasources:query` remains uid-scoped;
- prove writes remain refused, using harmless write requests against test endpoints;
- confirm the basic role is still `None` and `chats:access` is absent.

Rotation is an explicit provisioner operation. Confirm the new SSM value works before deleting the old token. Teardown and repair use recorded ids, never a name pattern.

## Credential and policy checks

The project owns exactly the access policies explicitly created for its reader, writer and provisioner. **Never update or delete another access policy while operating this platform.**

Use IAM policy simulation to prove the Infinity principal is allowed on `views/*` and denied on `scans/*` and `locks/*`.

For `ssm:GetParametersByPath`, test the bare path ARN as well as a child ARN. The API authorises the path itself, so a simulation against a child ARN alone can pass while the real call is denied.

## Cost allocation

```bash
bin/check-tags.sh          # audit the cost-allocation tag
bin/check-tags.sh --fix    # repair it
```

## Proving a headline

```bash
python3 bin/trace.py --live --context <gcx-context>
```

Every headline figure reproduces from the raw scan. `bin/probe_usage_signals.py` re-measures the `grafanacloud-usage` panels and needs no credential.
