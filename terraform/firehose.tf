# Optional CloudWatch Logs -> AWS Data Firehose -> Grafana Cloud Loki delivery path.
#
# This path exists for the failures the collector cannot report about itself: an image that will not
# start, an unhandled traceback before emit, a credential/bootstrap error, or an OOM kill. It is
# deliberately independent of the collector's native Loki writer and is OFF by default.
#
# Deployment is two-stage. `firehose_logs_enabled` creates everything through the delivery stream, but
# does not subscribe the live ECS log group. Test one delivery and confirm both the secret VALUE shape
# and the derived Grafana endpoint first. Only then set `firehose_log_subscription_enabled = true`.
# A bad access-key shape is accepted at apply time and fails only at delivery time, into the S3 backup.

# --- Failed-record S3 backup ----------------------------------------------------------------------

resource "aws_s3_bucket" "firehose_failed" {
  count = var.firehose_logs_enabled ? 1 : 0

  bucket = local.firehose_backup_bucket_name
  tags   = local.tags
}

resource "aws_s3_bucket_public_access_block" "firehose_failed" {
  count = var.firehose_logs_enabled ? 1 : 0

  bucket                  = aws_s3_bucket.firehose_failed[0].id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "firehose_failed" {
  count = var.firehose_logs_enabled ? 1 : 0

  bucket = aws_s3_bucket.firehose_failed[0].id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "firehose_failed" {
  count = var.firehose_logs_enabled ? 1 : 0

  bucket = aws_s3_bucket.firehose_failed[0].id

  rule {
    id     = "expire-failed-deliveries"
    status = "Enabled"

    filter {}

    expiration {
      days = var.firehose_failed_record_retention_days
    }

    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

data "aws_iam_policy_document" "firehose_failed_bucket" {
  count = var.firehose_logs_enabled ? 1 : 0

  statement {
    sid    = "DenyInsecureTransport"
    effect = "Deny"

    principals {
      type        = "*"
      identifiers = ["*"]
    }

    actions = ["s3:*"]
    resources = [
      aws_s3_bucket.firehose_failed[0].arn,
      "${aws_s3_bucket.firehose_failed[0].arn}/*",
    ]

    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "firehose_failed" {
  count = var.firehose_logs_enabled ? 1 : 0

  bucket = aws_s3_bucket.firehose_failed[0].id
  policy = data.aws_iam_policy_document.firehose_failed_bucket[0].json

  depends_on = [aws_s3_bucket_public_access_block.firehose_failed]
}

# --- Firehose delivery identity -------------------------------------------------------------------

data "aws_iam_policy_document" "firehose_assume" {
  count = var.firehose_logs_enabled ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["firehose.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }
  }
}

resource "aws_iam_role" "firehose" {
  count = var.firehose_logs_enabled ? 1 : 0

  name               = "${var.name_prefix}-firehose"
  assume_role_policy = data.aws_iam_policy_document.firehose_assume[0].json
  tags               = local.tags
}

data "aws_iam_policy_document" "firehose" {
  count = var.firehose_logs_enabled ? 1 : 0

  statement {
    sid    = "WriteFailedRecords"
    effect = "Allow"
    actions = [
      "s3:AbortMultipartUpload",
      "s3:GetObject",
      "s3:PutObject",
    ]
    resources = ["${aws_s3_bucket.firehose_failed[0].arn}/*"]
  }

  statement {
    sid    = "InspectFailedRecordBucket"
    effect = "Allow"
    actions = [
      "s3:GetBucketLocation",
      "s3:ListBucket",
      "s3:ListBucketMultipartUploads",
    ]
    resources = [aws_s3_bucket.firehose_failed[0].arn]
  }

  statement {
    sid       = "ReadDedicatedGrafanaAccessKey"
    effect    = "Allow"
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.firehose_access_key_secret_arn]
  }

  dynamic "statement" {
    for_each = var.firehose_access_key_secret_kms_key_arn == "" ? [] : [1]

    content {
      sid    = "DecryptDedicatedGrafanaAccessKey"
      effect = "Allow"
      actions = [
        "kms:Decrypt",
        "kms:DescribeKey",
      ]
      resources = [var.firehose_access_key_secret_kms_key_arn]
    }
  }
}

resource "aws_iam_role_policy" "firehose" {
  count = var.firehose_logs_enabled ? 1 : 0

  name   = "deliver-ecs-logs"
  role   = aws_iam_role.firehose[0].id
  policy = data.aws_iam_policy_document.firehose[0].json
}

# --- Delivery stream ------------------------------------------------------------------------------

resource "aws_kinesis_firehose_delivery_stream" "ecs_logs" {
  count = var.firehose_logs_enabled ? 1 : 0

  name        = "${var.name_prefix}-ecs-logs"
  destination = "http_endpoint"
  tags        = local.tags

  lifecycle {
    precondition {
      # Firehose cannot select one JSON key from the collector's existing multi-value secret. Requiring
      # a real ARN here prevents the default empty value becoming a delivery-time auth failure.
      condition = can(regex(
        "^arn:${data.aws_partition.current.partition}:secretsmanager:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:secret:.+$",
        var.firehose_access_key_secret_arn,
      ))
      error_message = "firehose_access_key_secret_arn must be a Secrets Manager secret ARN in this account and region when firehose_logs_enabled is true."
    }
  }

  http_endpoint_configuration {
    url      = local.firehose_loki_endpoint
    name     = "Grafana Cloud Loki"
    role_arn = aws_iam_role.firehose[0].arn

    buffering_size     = 1
    buffering_interval = 60
    s3_backup_mode     = "FailedDataOnly"

    # The adopted secret carries the endpoint access key in the `api_key` JSON field required by
    # Firehose for HTTP destinations. There is deliberately no `access_key` attribute anywhere in this
    # module: that would put the logs-write credential into state.
    secrets_manager_configuration {
      enabled    = true
      secret_arn = var.firehose_access_key_secret_arn
      role_arn   = aws_iam_role.firehose[0].arn
    }

    request_configuration {
      content_encoding = "GZIP"

      # Grafana strips `lbl_` when these become Loki labels. Every value below is bounded to one value
      # per module instantiation. Task ARN/id, container id and image digest remain in the record body.
      common_attributes {
        name  = "lbl_job"
        value = var.name_prefix
      }

      common_attributes {
        name  = "lbl_service_name"
        value = var.name_prefix
      }

      common_attributes {
        name  = "lbl_tier"
        value = "ecs"
      }

      common_attributes {
        name  = "lbl_env"
        value = local.firehose_log_environment
      }

      common_attributes {
        name  = "lbl_aws_account"
        value = data.aws_caller_identity.current.account_id
      }
    }

    s3_configuration {
      role_arn           = aws_iam_role.firehose[0].arn
      bucket_arn         = aws_s3_bucket.firehose_failed[0].arn
      buffering_size     = 1
      buffering_interval = 60
      compression_format = "GZIP"
      error_output_prefix = join("", [
        "failed/",
        "!{firehose:error-output-type}/",
        "!{timestamp:yyyy/MM/dd}/",
      ])
    }
  }

  depends_on = [aws_iam_role_policy.firehose]
}

# --- CloudWatch Logs subscription identity --------------------------------------------------------

data "aws_iam_policy_document" "firehose_subscription_assume" {
  count = var.firehose_logs_enabled ? 1 : 0

  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["logs.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [data.aws_caller_identity.current.account_id]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:SourceArn"
      # Normal delivery assumes this role with the concrete log-stream source ARN. The subscription
      # control probe uses the bare log-group ARN, so an exact match can pass creation while every
      # real event fails with AWS/Logs DeliveryErrors. Retain log-group scope and admit its streams.
      values = ["${aws_cloudwatch_log_group.tasks.arn}:*"]
    }
  }
}

resource "aws_iam_role" "firehose_subscription" {
  count = var.firehose_logs_enabled ? 1 : 0

  name               = "${var.name_prefix}-logs-subscription"
  assume_role_policy = data.aws_iam_policy_document.firehose_subscription_assume[0].json
  tags               = local.tags
}

data "aws_iam_policy_document" "firehose_subscription" {
  count = var.firehose_logs_enabled ? 1 : 0

  statement {
    sid    = "WriteECSLogsToFirehose"
    effect = "Allow"
    actions = [
      "firehose:PutRecord",
      "firehose:PutRecordBatch",
    ]
    resources = [aws_kinesis_firehose_delivery_stream.ecs_logs[0].arn]
  }
}

resource "aws_iam_role_policy" "firehose_subscription" {
  count = var.firehose_logs_enabled ? 1 : 0

  name   = "write-ecs-logs-to-firehose"
  role   = aws_iam_role.firehose_subscription[0].id
  policy = data.aws_iam_policy_document.firehose_subscription[0].json
}

# The only resource controlled by the second-stage switch. Keeping this separate is the safety seam:
# the stream can accept a deliberate DirectPut test before any customer task log is wired to it.
resource "aws_cloudwatch_log_subscription_filter" "ecs_logs" {
  count = var.firehose_log_subscription_enabled ? 1 : 0

  name            = "${var.name_prefix}-ecs-logs"
  log_group_name  = aws_cloudwatch_log_group.tasks.name
  filter_pattern  = ""
  destination_arn = var.firehose_logs_enabled ? aws_kinesis_firehose_delivery_stream.ecs_logs[0].arn : ""
  role_arn        = var.firehose_logs_enabled ? aws_iam_role.firehose_subscription[0].arn : ""

  lifecycle {
    precondition {
      condition     = var.firehose_logs_enabled
      error_message = "firehose_log_subscription_enabled requires firehose_logs_enabled; create and test the delivery stream first."
    }
  }

  depends_on = [aws_iam_role_policy.firehose_subscription]
}
