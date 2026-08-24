# EventBridge Scheduler, one schedule per enabled tier.
#
# Scheduler rather than the older EventBridge Rules + ECS target: a single IAM role, a real retry
# policy, and `state` as a first-class field so a tier can be paused without destroying it.
#
# NEITHER mechanism deduplicates. If a run overruns its interval, the next fire starts a second task
# against the same estate and the same rate-limit quota, and whichever finishes LAST wins the
# `latest.json` write regardless of which started first - so the estate can silently go backwards in
# time. That is prevented in the collector, by a per-tier S3 lock, not here. There is no scheduler
# setting that would do it.

resource "aws_scheduler_schedule" "scan" {
  for_each = var.tiers

  name        = "${var.name_prefix}-${each.key}"
  description = each.value.description != "" ? each.value.description : "${var.name_prefix} ${each.key} scan"
  group_name  = "default"

  schedule_expression          = each.value.schedule_expression
  schedule_expression_timezone = var.schedule_timezone
  state                        = local.schedule_state[each.key]

  flexible_time_window {
    # OFF, so the schedule fires at the stated minute. A flexible window would let two tiers drift into
    # each other, and they share one rate-limit quota because it is metered per credential.
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.this.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.scan[each.key].arn
      launch_type         = "FARGATE"
      task_count          = 1
      # Pinned rather than LATEST so a Fargate platform release cannot change the runtime under a
      # working schedule.
      #
      # 1.4.0 IS A FLOOR, NOT A PREFERENCE. Injecting a *single JSON key* of a Secrets Manager secret
      # requires platform 1.4.0+ on Linux; 1.3.0 can only inject a whole secret. The task definitions
      # reference `<arn>:KEY::`, so lowering this makes both credentials arrive wrong rather than
      # failing loudly.
      platform_version        = "1.4.0"
      enable_ecs_managed_tags = true
      propagate_tags          = "TASK_DEFINITION"

      network_configuration {
        subnets          = var.subnet_ids
        security_groups  = local.security_group_ids
        assign_public_ip = var.assign_public_ip
      }
    }

    retry_policy {
      # Retries a failed RunTask *invocation* - the API call that starts the task. It does NOT re-run a
      # scan that started and exited non-zero, which is the behaviour we want: a scan that failed on
      # coverage would spend the same rate-limit budget against the same wall a second time, and the
      # dead-man's switch is what escalates instead.
      maximum_retry_attempts       = var.schedule_retry_attempts
      maximum_event_age_in_seconds = 300
    }
  }
}
