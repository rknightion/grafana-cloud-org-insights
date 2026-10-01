# Running scans

## Before the first scheduled scan

Tell the write-stack owner that this platform adds active series to that one stack. Measure the footprint with a range query against the write stack itself; the organisation total is not the denominator. Also confirm that the deploying organisation accepts clear identity data in S3 and Loki.

Do not enable schedules until:

1. the Secrets Manager object contains separate read, write and provisioner token keys;
2. the image is available at the immutable digest pinned by Terraform;
3. the S3 bucket and stack-token SSM path exist with the intended IAM boundaries;
4. the provisioner has reconciled and verified the stack-local readers;
5. one manual run of each scan tier has advanced its envelope;
6. the dashboards and new paused, unrouted alert rules have been published with a short-lived build token.

These are prerequisites, not authority to perform live changes. Each live scan, provisioning run,
publish or schedule change needs separate authorization. See the [runbook timetable](../RUNBOOK.md#scheduled-jobs)
for all five jobs: module defaults are T1 hourly at :05, T2 daily, T3 six-hourly, T4 daily and a daily
opt-in provisioner. Deployment cron and timezone overrides must be checked in the manifest and live
Scheduler state; the module timezone default is UTC.

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

Exit `4` is a lock collision, not a failed scan. Do not disable a schedule to work around it. A limited `--stack` or `--limit` run requires `--dry-run` for diagnostics; without it the scanner refuses publication.
With it, no S3, Mimir or Loki writes occur.

## The provisioner

The provisioner (daily by module default, opt-in with `create_provisioner = true`) reconciles a basic-role-`None` service account and the `custom:gcinsight.reader` role on every provisionable live stack. Drift is compared as action/scope pairs, not action names.

**Healthy steady state is reads with no token mint.** A repair creates a transient Admin identity, records its ids, repairs the role and assignment, verifies them, and deletes the Admin identity last.

The repair path must not mint when the stored token still works. Token names are organisation-wide unique, so an unnecessary mint can create a timestamped credential and orphan the original.

After changing the role:

- compare action/scope pairs, not action names;
- allow for partial RBAC propagation before testing the existing token;
- verify `datasources:query` remains uid-scoped;
- prove writes remain refused, using harmless write requests against test endpoints;
- confirm the basic role is still `None` and `chats:access` is absent.

The provisioner CLI has no rotation or teardown command. Separately authorized rotation must verify
the replacement SSM value before deleting the old token. Teardown and repair use recorded ids, never
a name pattern; retain authorized Admin access until custom roles are removed.

## Credential and policy checks

The project owns exactly the access policies explicitly created for its reader, writer and provisioner. **Never update or delete another access policy while operating this platform.**

Use IAM policy simulation to prove the Infinity principal is allowed on `views/*` and denied on `scans/*` and `locks/*`.

For `ssm:GetParametersByPath`, test the bare path ARN as well as a child ARN. The API authorises the path itself, so a simulation against a child ARN alone can pass while the real call is denied.

## Cost allocation

```bash
just check-tags          # live read-only audit; requires NAME_PREFIX and GCINSIGHT_S3_BUCKET
just check-tags --fix    # live repair; requires separate authorization
```

## Proving a headline

```bash
python3 bin/trace.py --live --context <gcx-context>
```

The tracer independently recomputes its declared headline figures from the raw scan and exits 1 on
mismatch; it does not cover every panel. `bin/probe_usage_signals.py` re-measures the
`grafanacloud-usage` signals with `python3 bin/probe_usage_signals.py --context <gcx-context> --out
<new-artifact.json>`. It needs no additional service-account or CAP token, but it is a live read.
`--help` is side-effect-free; a live run requires both arguments and refuses an existing output unless
`--overwrite` explicitly permits replacement. Keep live output separate from committed synthetic
artifacts.
