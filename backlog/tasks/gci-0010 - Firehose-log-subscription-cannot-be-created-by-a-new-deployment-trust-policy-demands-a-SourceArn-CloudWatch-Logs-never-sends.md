---
id: GCI-0010
title: >-
  Firehose log subscription cannot be created by a new deployment - trust policy
  demands a SourceArn CloudWatch Logs never sends
status: To Do
assignee: []
created_date: '2026-08-25 08:27'
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
- [ ] #1 The logs-subscription role trust policy matches the SourceArn CloudWatch Logs actually sends, so a first-time apply creates the subscription filter without manual intervention
- [ ] #2 The condition still constrains the role to this deployment log group and account - the fix is not to drop the condition
- [ ] #3 Verified by creating the filter against a log group that has never had one, not by an existing deployment where the condition is no longer evaluated
- [ ] #4 RUNBOOK and troubleshooting entries describing the misleading ACTIVE-state error are updated or removed once the fix lands
<!-- AC:END -->

## Definition of Done
<!-- DOD:BEGIN -->
- [ ] #1 python3 -m pytest tests -q
- [ ] #2 tofu fmt -check -recursive terraform; tofu init -backend=false and tofu validate pass for terraform/ and terraform/examples/standalone/
- [ ] #3 customer-identifier and shipped-text gates from .github/workflows/ci.yml return clean
<!-- DOD:END -->
