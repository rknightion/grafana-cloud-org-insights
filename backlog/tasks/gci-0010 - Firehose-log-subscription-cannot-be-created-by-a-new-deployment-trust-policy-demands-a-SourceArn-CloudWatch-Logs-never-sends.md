---
id: GCI-0010
title: >-
  Firehose log subscription cannot be created by a new deployment - trust policy
  demands a SourceArn CloudWatch Logs never sends
status: Done
assignee:
  - '@loop3-root'
created_date: '2026-08-25 08:27'
updated_date: '2026-09-30 15:05'
labels:
  - bug
dependencies: []
priority: high
ordinal: 17000
---

## Description

<!-- SECTION:DESCRIPTION:BEGIN -->
The `firehose_log_subscription_enabled` path is unusable for anyone standing up a NEW deployment. `aws_cloudwatch_log_subscription_filter` fails at apply with:

```
InvalidParameterException: Could not deliver test message to specified Firehose stream.
Check if the given Firehose stream is in ACTIVE state.
```

The stream IS ACTIVE and the message is misleading. The real failure is the AssumeRole behind CloudWatch Logs test message. CloudWatch Logs assumes the subscription role passing the BARE log-group ARN as `aws:SourceArn`, while `terraform/firehose.tf` builds the trust condition as `ArnLike aws:SourceArn = <log-group-arn>:*`, so the condition never matches.

Isolated live against a throwaway role, three variants, same log group and same stream:

| Trust condition | Result |
|---|---|
| `StringEquals aws:SourceAccount` only | WORKS |
| `ArnLike aws:SourceArn = <log-group-arn>:*` | BLOCKED |
| `ArnLike aws:SourceArn = <log-group-arn>` (no `:*`) | WORKS |

Everything else on the path is fine, which is what makes the error so misleading: a manual `aws firehose put-record` on the same stream gave `DeliveryToHttpEndpoint.Success = 1` with an empty failed-record bucket, so the endpoint, the adopted secret `<tenant>:<token>` shape, the Firehose delivery role and its Secrets Manager read are all correct.

WHY THIS HAS BEEN INVISIBLE, AND WHY IT MATTERS NOW. The trust condition is evaluated only when a subscription filter is CREATED. An existing filter keeps working for ever, so an established deployment shows no symptom and gives false assurance that the path works. Every new deployment hits it. It will bite hardest exactly where the module advertises support - a second organisation deployed into the same AWS account beside an existing one - because the existing deployment furnishes the evidence that the feature works.

Found while standing up a second deployment beside an existing one in a shared account. That deployment currently runs with the subscription disabled; its ECS task logs stay in CloudWatch and only the copy to Loki is missing.
<!-- SECTION:DESCRIPTION:END -->

## Acceptance Criteria
<!-- AC:BEGIN -->
- [x] #1 The logs-subscription role trust policy matches the SourceArn CloudWatch Logs actually sends, so a first-time apply creates the subscription filter without manual intervention
- [x] #2 The condition still constrains the role to this deployment log group and account - the fix is not to drop the condition
- [x] #3 Verified by creating the filter against a log group that has never had one, not by an existing deployment where the condition is no longer evaluated
- [x] #4 RUNBOOK and troubleshooting entries describing the misleading ACTIVE-state error are updated or removed once the fix lands
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [x] #1 python3 -m pytest tests -q
- [x] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [x] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->

## Implementation Plan

<!-- SECTION:PLAN:BEGIN -->
Fix the Firehose trust SourceArn condition using the bare log-group ARN, validate both Terraform roots, update troubleshooting documentation, and park the live first-filter criterion with its exact operator command because AWS writes are forbidden.

loop3 R-0010: targeted ephemeral instance of exact generic module on staff dev, new log group proven absent beforehand. Create stream, prove delivery, then enable real module subscription filter without manual intervention; read back trust/filter, remove only recorded probe resources by reviewed saved destroy plan.
<!-- SECTION:PLAN:END -->

## Implementation Notes

<!-- SECTION:NOTES:BEGIN -->
Wave 1 implementation and deterministic verification completed. Acceptance criterion 3 requires a write to an AWS deployment and was outside the run authority. Resume by applying a consumer deployment with firehose_logs_enabled=true and firehose_log_subscription_enabled=true against a log group that has never carried a subscription filter, then verify aws_cloudwatch_log_subscription_filter.ecs_logs is created without manual intervention.

Wave 2 attended acceptance did not run because the operator did not supply the required consumer deployment and fresh log-group identity during the run. No deployment was inferred. Acceptance criterion 3 remains unproved.

loop3 admitted 2026-09-30 under owner goal: root owns tracker; bounded lanes own implementation/discovery, evidence pending. No acceptance claimed yet.
<!-- SECTION:NOTES:END -->

## Final Summary

<!-- SECTION:FINAL_SUMMARY:BEGIN -->
The trust policy now matches the bare log-group ARN CloudWatch Logs sends while retaining SourceAccount and the deployment-specific log-group constraint. RUNBOOK and troubleshooting guidance were corrected. Terraform tests and both validate roots passed at b6cf849614054894e2bea49d0154d958fc016d7b. Parked only on the required first-filter live AWS apply.

Wave 2 left the task Parked: the required consumer deployment and fresh log group were not supplied, so no first-time subscription-filter creation was attempted or observed.

loop3 R-0010 completed the missing first-time proof using exact generic57d39ed7f3ae0bacf9630990f7437f293fa7a91b in an isolated staff-dev module. Fresh log group witnessed absent before create; real saved module plan/apply created its first subscription filter without manual intervention, then actual filter and exact bare log-group/account trust read back. Targeted replan No changes. Synthetic delivery read back in Loki by service_name (endpoint reserves job=cloud/aws), failed backup empty. Three reviewed applies created9, created3, destroyed12 probe resources only; post-teardown loggroup/stream/bucket/both roles absence verified. No baseline deployment changed. Evidence codex/loop3-evidence/R-0010; expected tiny-probe cost under1 dollar, no recurring resource left.
<!-- SECTION:FINAL_SUMMARY:END -->
