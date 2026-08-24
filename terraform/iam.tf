# Four principals, each with the narrowest job that still works:
#
#   execution role  ECS agent's identity. Pulls the image, writes log streams, and resolves the two
#                   secret JSON keys. It never runs collector code.
#   task role       the collector's own identity. S3 on four working prefixes plus read-only access to
#                   the exact optional rate-card key. NOTHING else  -  it does not read the secret (the
#                   agent injects it) and its Grafana Cloud permissions come from tokens, not IAM.
#   scheduler role  EventBridge Scheduler's identity. RunTask on the four scan task definitions plus
#                   the optional provisioner, and PassRole limited to their exact task/execution roles.
#   views reader    the Grafana Infinity datasource's user. GetObject on views/* only.
#
# The separation that actually matters is the last one: `scans/` holds per-user identity detail, and a
# dashboard datasource has no business reading it.

# --- Execution role --------------------------------------------------------------------------------

data "aws_iam_policy_document" "ecs_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }

    # Confused-deputy guard: without this, any ECS task in any account that could somehow reference
    # this role ARN could assume it. Standard practice and free.
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "execution" {
  name               = "${var.name_prefix}-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

resource "aws_iam_role_policy_attachment" "execution_managed" {
  role       = aws_iam_role.execution.name
  policy_arn = "arn:${data.aws_partition.current.partition}:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "execution_secrets" {
  statement {
    sid       = "ReadCollectorTokens"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [local.secret_arn]
  }
}

resource "aws_iam_role_policy" "execution_secrets" {
  name   = "read-collector-tokens"
  role   = aws_iam_role.execution.id
  policy = data.aws_iam_policy_document.execution_secrets.json
}

# --- Task role -------------------------------------------------------------------------------------

resource "aws_iam_role" "task" {
  name               = "${var.name_prefix}-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "task" {
  statement {
    sid    = "ReadWriteScanStorage"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:GetObject",
      # DeleteObject is needed only to RELEASE a lock. Without it every run leaves its lock behind and
      # the next run of that tier refuses to start until the TTL expires  -  which looks exactly like a
      # scheduling bug and is an IAM one.
      "s3:DeleteObject",
    ]

    resources = [
      "${local.bucket_arn}/scans/*",
      "${local.bucket_arn}/views/*",
      "${local.bucket_arn}/locks/*",
      # `state/` holds the slower tier's saved metric batch, which the hourly tier republishes so panels
      # resolve between runs. Omitting it does not fail the scan: carry-forward degrades to "no t3 state"
      # and the run exits 0 after publishing only its hourly series.
      "${local.bucket_arn}/state/*",
    ]
  }

  statement {
    sid       = "ReadRateCard"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/config/ratecard.csv"]
  }

  statement {
    sid    = "ListForBaselineSelection"
    effect = "Allow"
    # The T4 diff lists `scans/<tier>/` to find the scan nearest T-7d. Without List it cannot select a
    # baseline and reports "no baseline"  -  a correct-looking message with an IAM cause.
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]
  }
}

resource "aws_iam_role_policy" "task" {
  name   = "scan-storage"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.task.json
}

# --- Per-stack credential store (PLAN 17D) ---------------------------------------------------------
#
# One SSM `SecureString` per stack at `/gcinsight/stack-token/<slug>`, holding that stack's
# read-only reader token plus the ids needed to reconcile it.
#
# **SSM, not Secrets Manager, and the reason is cost at this fan-out.** Secrets Manager is $0.40 per
# secret per month, which is needlessly expensive at estate scale. SSM standard-tier parameters are
# free; KMS request cost depends on the configured key and request volume.
#
# **One parameter per stack, never one estate-wide JSON blob.** A blob makes every provisioning write a
# read-modify-write against a single object  -  the provisioner racing any manual repair  -  and gives the
# whole estate one blast radius.
#
# The split below is the control that matters: the COLLECTOR can only read, and only the provisioner
# task can write or delete. A bug in the collector cannot destroy the credential store.

data "aws_iam_policy_document" "stack_tokens_read" {
  statement {
    sid     = "ReadStackTokens"
    effect  = "Allow"
    actions = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    # BOTH ARNs are required. `GetParametersByPath` authorises the path ARN itself; individual reads
    # authorise child parameter ARNs. Omitting either silently breaks one of those access shapes.
    resources = [
      local.stack_token_arn_prefix,
      "${local.stack_token_arn_prefix}/*",
    ]
  }

  statement {
    sid    = "DecryptStackTokens"
    effect = "Allow"
    # SecureString parameters are sealed with the account's `aws/ssm` managed key. Without Decrypt the
    # GetParameter call succeeds and returns ciphertext, which fails later as an auth error against
    # Grafana rather than as an IAM error here  -  the same class of misleading failure as the missing
    # `state/*` prefix above.
    actions   = ["kms:Decrypt"]
    resources = ["*"]

    condition {
      # StringLike, NOT StringEquals: the value is a wildcard prefix, and StringEquals compares the
      # `*` literally so no real parameter ARN would ever match. The failure would not appear here  -  the
      # policy applies cleanly and Decrypt is silently denied at runtime, surfacing as a Grafana auth
      # error. Caught in review before the first Fargate run.
      test     = "StringLike"
      variable = "kms:EncryptionContext:PARAMETER_ARN"
      values   = ["${local.stack_token_arn_prefix}/*"]
    }
  }
}

resource "aws_iam_role_policy" "task_stack_tokens" {
  name   = "read-stack-tokens"
  role   = aws_iam_role.task.id
  policy = data.aws_iam_policy_document.stack_tokens_read.json
}

# --- Provisioner role ------------------------------------------------------------------------------
#
# Separate role from the collector, deliberately. The provisioner holds the only credential in this
# project that can write to gcom (`stack-service-accounts:write`), so it is a separate task with a
# separate role and the collector never gets either.

resource "aws_iam_role" "provisioner" {
  count = var.create_provisioner ? 1 : 0

  name               = "${var.name_prefix}-provisioner"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "provisioner" {
  count = var.create_provisioner ? 1 : 0

  statement {
    sid    = "ReadStackTokens"
    effect = "Allow"
    actions = [
      "ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath",
    ]
    # Same `GetParametersByPath` rule as the collector's read statement above: the provisioner LISTS the
    # store to find credentials whose stack has left the estate, so without the bare path ARN pruning
    # cannot see anything to prune - and a prune that finds nothing looks exactly like a prune with
    # nothing to do.
    resources = [
      local.stack_token_arn_prefix,
      "${local.stack_token_arn_prefix}/*",
    ]
  }

  statement {
    sid    = "WriteStackTokens"
    effect = "Allow"
    actions = [
      "ssm:PutParameter",
      # Needed to prune a credential whose stack has left the estate. There is no gcom delete in that
      # path  -  a deleted stack takes its service accounts with it  -  so this is the whole of pruning.
      "ssm:DeleteParameter",
    ]
    # The bare prefix above exists only for GetParametersByPath authorization. A token write always
    # targets a child parameter, so keep mutation rights off the prefix object itself.
    resources = ["${local.stack_token_arn_prefix}/*"]
  }

  statement {
    sid       = "EncryptAndDecryptStackTokens"
    effect    = "Allow"
    actions   = ["kms:Decrypt", "kms:Encrypt", "kms:GenerateDataKey"]
    resources = ["*"]

    condition {
      # StringLike, NOT StringEquals: the value is a wildcard prefix, and StringEquals compares the
      # `*` literally so no real parameter ARN would ever match. The failure would not appear here  -  the
      # policy applies cleanly and Decrypt is silently denied at runtime, surfacing as a Grafana auth
      # error. Caught in review before the first Fargate run.
      test     = "StringLike"
      variable = "kms:EncryptionContext:PARAMETER_ARN"
      values   = ["${local.stack_token_arn_prefix}/*"]
    }
  }
}

resource "aws_iam_role_policy" "provisioner" {
  count = var.create_provisioner ? 1 : 0

  name   = "write-stack-tokens"
  role   = aws_iam_role.provisioner[0].id
  policy = data.aws_iam_policy_document.provisioner[0].json
}

# --- Scheduler role --------------------------------------------------------------------------------

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name_prefix}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "scheduler" {
  statement {
    sid    = "RunScanTasks"
    effect = "Allow"
    # RunTask is granted against the task definitions without a revision suffix plus `:*`, because a
    # schedule targets a specific revision and every `terraform apply` that changes a task definition
    # creates a new one. Pinning a single revision here means the FIRST image update silently breaks
    # every schedule with an AccessDenied that surfaces only in the schedule's own failure metric.
    actions = ["ecs:RunTask"]
    resources = concat(
      [for t in aws_ecs_task_definition.scan : "${t.arn_without_revision}:*"],
      [for t in aws_ecs_task_definition.provisioner : "${t.arn_without_revision}:*"],
    )

    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }

  statement {
    sid    = "PassTaskRoles"
    effect = "Allow"
    # Scheduler hands these to ECS when starting a task. Scoped to exactly the scan execution/task roles
    # plus the optional provisioner's task role: an unscoped PassRole here would let anything that can
    # edit a schedule run a task as any role in the account.
    actions = ["iam:PassRole"]
    resources = concat(
      [aws_iam_role.execution.arn, aws_iam_role.task.arn],
      aws_iam_role.provisioner[*].arn,
    )

    condition {
      test     = "StringEquals"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  statement {
    sid       = "TagStartedTasks"
    effect    = "Allow"
    actions   = ["ecs:TagResource"]
    resources = ["*"]

    # Required because the schedules set enable_ecs_managed_tags. ECS tags the task it creates, whose
    # ARN cannot be known in advance, so this cannot be resource-scoped  -  the cluster condition is what
    # bounds it.
    condition {
      test     = "ArnEquals"
      variable = "ecs:cluster"
      values   = [aws_ecs_cluster.this.arn]
    }
  }
}

resource "aws_iam_role_policy" "scheduler" {
  name   = "run-scan-tasks"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler.json
}

# --- Grafana views reader --------------------------------------------------------------------------

resource "aws_iam_user" "views_reader" {
  count = var.create_views_reader_user ? 1 : 0

  name = "${var.name_prefix}-views-ro"
  tags = local.tags
}

data "aws_iam_policy_document" "views_reader" {
  count = var.create_views_reader_user ? 1 : 0

  statement {
    sid       = "ReadViewsOnly"
    effect    = "Allow"
    actions   = ["s3:GetObject"]
    resources = ["${local.bucket_arn}/views/*"]
  }

  # ListBucket is scoped by prefix so the datasource cannot even enumerate `scans/`. Object-level deny
  # alone would still leak the key names, which for this platform means stack slugs and scan times.
  statement {
    sid       = "ListViewsPrefixOnly"
    effect    = "Allow"
    actions   = ["s3:ListBucket"]
    resources = [local.bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["views/*"]
    }
  }
}

resource "aws_iam_user_policy" "views_reader" {
  count = var.create_views_reader_user ? 1 : 0

  name   = "read-views"
  user   = aws_iam_user.views_reader[0].name
  policy = data.aws_iam_policy_document.views_reader[0].json
}

# No aws_iam_access_key resource: it would put a long-lived secret in Terraform state. Mint it with
# `aws iam create-access-key --user-name <name>` and store it next to the Grafana tokens.
