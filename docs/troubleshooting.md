# Troubleshooting

Most of these look like missing data and are not.

## An empty periodic Prometheus panel

Confirm it is a range query reduced with `lastNotNull`. An instant query against a periodic collector metric is empty outside Mimir's lookback delta, and renders exactly like a metric that was never written.

## T2 or T3 data missing in a six-hour dashboard window

Inspect hydration and the owning scan envelope. Every tier composes the full view set by hydrating inputs it does not own from the owning tier's latest envelope, so a stalled T3 shows up as gaps in a T1-published view.

A view whose inputs are unsatisfied is withheld, leaving the last good S3 object visible with its older timestamp. A table that stops advancing is the signal.

## A confident zero from a list endpoint

Several stack-local list endpoints return HTTP 200 with a permission-filtered empty list. Confirm the matching role action/scope pair is present before trusting the response.

The Loki ruler is the inverse case: it answers **404 with `no rule groups found`** when a stack has no rules. That is an empty inventory, not a permission failure. `/prometheus/api/v1/rules` on the same host returns 200 with an empty group list for the same stack.

## Usage-insights values repeated across stacks

Inspect the `instance_id` selector immediately. Each stack's usage-insights datasource exposes a whole region, so a selector missing `instance_id` returns the region's data for every stack in it. The query helper refuses a selector without the regional guard; a hand-written query bypasses that.

## An Adaptive saving that equals all series on unadopted stacks

Confirm the recommendations were requested with `?verbose=true`, and check the marginal arithmetic. Remediable series are the sum of positive `current_series_count - recommended_series_count` reductions for `add` and `update` actions only. `keep` and `remove` are not unrealised reductions.

An unknown action or a missing before/after pair makes the aggregate unavailable, not zero.

## Currency missing from a value panel

Absence is correct when the card or that dimension is unpriced - `price()` returns `None`, never `0.0`. Inspect the disclosure: a partially priced card names the omitted components and must not present its subtotal as a complete estate total.

## A per-stack sweep comes back empty

Simulate SSM access on the bare token-prefix ARN, not only on a child ARN. `ssm:GetParametersByPath` authorises the path itself.

## The provisioner performs widespread writes on a healthy estate

Stop and inspect the drift and mint classification. Healthy steady state is reads with no token mint, and the repair path must not mint while the stored token still works.

Token names are organisation-wide unique, so an unnecessary mint creates a timestamped credential and orphans the original.

## T4 reports movement after a coverage change

Compare measured populations before calling it estate movement. A change in how many stacks were scannable moves the diff without anything in the estate having moved.

## Exit code 4

A lock collision - another scan holds the lock. It is not a failed scan, and disabling a schedule is not the fix.

## Coverage never reaches 100%

Coverage is a ratio against **scannable** stacks. Paused stacks answer the control plane with a conflict response and are skipped, not failed. If a deployment computes coverage against the total instead, a handful of paused stacks caps it below 100% for ever.

## Tasks fail to start immediately after the first apply

Almost always ordering. See [Deployment](deployment.md) for the steps in order. The two that bite hardest: an x86 image on an ARM64 task definition fails at runtime with `exec format error` rather than at plan time, and schedules enabled before the secret is populated produce four failing tasks an hour whose first symptom is a CloudWatch bill.

## T2 exits 1 at coverage 0.0 on a brand-new deployment

The provisioner has not run yet, and the reader token is fine.

Every stack-local source - service accounts, Assistant, usage insights, dashboard inventory, datasource query cost, Adaptive Logs, public dashboards, alert routing - reports `no_credential` and `0 of N available`, so the tier refuses all S3, Mimir and Loki writes. Those sources authenticate as the per-stack reader the provisioner mints into SSM, not as the org-realm reader, so none of them can work before it has run once. Run the provisioner, confirm one SSM parameter per stack, and re-run T2.

## `PutSubscriptionFilter` says the Firehose stream is not ACTIVE

The stream is ACTIVE. The message is misleading: what actually failed is CloudWatch Logs assuming the subscription role, because it passes the **bare log-group ARN** as `aws:SourceArn` and the trust policy matches `<log-group-arn>:*`.

This affects new deployments only - the condition is evaluated when the filter is created, so an existing filter keeps working and the problem stays invisible until the next deployment is stood up.

## `--publish all` raises `EmptyView`

A view with zero rows, on an estate small or clean enough to produce one. See *Empty views on a small estate* in the runbook: it is a current product limitation rather than a misconfiguration, and it cannot be worked around from a deployment.
