# Shared locals and the data sources everything else derives from.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}
data "aws_partition" "current" {}

locals {
  # `coalesce` treats "" as a present value, so an empty variable would beat the computed default.
  # Hence explicit emptiness checks rather than coalesce throughout.
  bucket_name = var.bucket_name != "" ? var.bucket_name : "${var.name_prefix}-data"
  secret_name = var.secret_name != "" ? var.secret_name : "${var.name_prefix}/tokens"

  bucket_arn = "arn:${data.aws_partition.current.partition}:s3:::${local.bucket_name}"

  # The Firehose endpoint is a property of the Loki write HOST, not of the stack's regionSlug or
  # clusterSlug. Prefixing the configured hostname is therefore both simpler and more correct than
  # reconstructing a host from unrelated control-plane inventory. `loki_write_url` is validated as an
  # origin above, so removing the scheme and optional trailing slash cannot retain a path.
  loki_hostname          = trimsuffix(trimprefix(var.loki_write_url, "https://"), "/")
  firehose_loki_endpoint = "https://aws-${local.loki_hostname}/aws-logs/api/v1/push"

  # Globally unique without asking the caller for another name. `name_prefix` is already the deployment
  # identity and the account suffix prevents a generic module consumer colliding with another account.
  firehose_backup_bucket_name = "${var.name_prefix}-fh-failed-${data.aws_caller_identity.current.account_id}"

  # Common attributes become Loki stream labels after Grafana drops the required `lbl_` prefix. The
  # shared CloudWatch group multiplexes every scanner tier, so `tier=ecs` is deliberately a bounded
  # source class; the actual t1/t2/t3/t4/provisioner stream name stays in the record body rather than
  # manufacturing one Firehose stream per tier. Environment is one fixed deployment value, not an
  # event-derived label.
  firehose_log_environment = lookup(var.tags, "Environment", "default")

  # Per-stack reader credentials (PLAN 17D). The path is also parsed back into a slug by
  # `bin/provision.py::ssm_list_slugs`, which is how pruning knows which stacks hold a credential - so
  # the trailing element must stay exactly the slug and nothing else.
  stack_token_prefix = var.stack_token_prefix
  stack_token_arn_prefix = join("", [
    "arn:${data.aws_partition.current.partition}:ssm:",
    data.aws_region.current.region,
    ":${data.aws_caller_identity.current.account_id}:parameter",
    local.stack_token_prefix,
  ])

  # A created secret's ARN is known from the resource; an adopted one must be looked up, because
  # Secrets Manager appends a random 6-character suffix to every ARN that cannot be derived from the
  # name. Getting this wrong yields a task that fails to start with an unhelpful ResourceNotFound.
  secret_arn = var.create_secret ? aws_secretsmanager_secret.tokens[0].arn : data.aws_secretsmanager_secret.tokens[0].arn

  # Resolves to "" rather than indexing a repository that was not created. Indexing it directly fails
  # with "Invalid index" while EVALUATING this local, which happens before any resource precondition can
  # run - so the readable error in ecs.tf only gets a chance if this expression stays safe.
  image = var.image != "" ? var.image : (
    var.create_ecr_repository ? "${aws_ecr_repository.collector[0].repository_url}:latest" : ""
  )

  security_group_ids = length(var.security_group_ids) > 0 ? var.security_group_ids : [aws_security_group.tasks[0].id]

  # EVERY tier gets a schedule; the switches set its STATE rather than its existence. Filtering disabled
  # tiers out instead would mean toggling one destroys and recreates the schedule, and `aws scheduler
  # list-schedules` would silently omit the tier you are trying to reason about - the two things you most
  # want when a tier has stopped running.
  #
  # Task definitions likewise exist for every tier regardless, so a disabled tier can still be run by
  # hand with `aws ecs run-task`, which is how the runbook backfills after an outage.
  schedule_state = {
    for name, cfg in var.tiers : name => (var.schedules_enabled && cfg.enabled) ? "ENABLED" : "DISABLED"
  }

  tags = var.tags
}
