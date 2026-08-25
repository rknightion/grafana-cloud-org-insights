variable "region" {
  description = "AWS region. Keep the bucket, tasks and secret in one region; there is no cross-region requirement."
  type        = string
  default     = "eu-west-1"
}

variable "name_prefix" {
  description = "Prefix for every resource. The only thing separating two deployments in one AWS account."
  type        = string
  default     = "estate-insights"
}

variable "grafana_org_id" {
  description = "Grafana Cloud organisation id to scan."
  type        = string
}

variable "write_stack_slug" {
  description = "Stack slug everything is published to."
  type        = string
}

variable "mimir_write_url" {
  description = "https://prometheus-prod-NN-<region>.grafana.net - from the stack's Prometheus datasource, minus the /api/prom path."
  type        = string
}

variable "mimir_tenant" {
  description = "The stack's hmInstancePromId. NOT the stack id - that fails as a 401."
  type        = string
}

variable "loki_write_url" {
  description = "https://logs-prod-NNN.grafana.net - from the stack's Loki datasource, minus the path."
  type        = string
}

variable "loki_tenant" {
  description = "The stack's hlInstanceId."
  type        = string
}

variable "subnet_ids" {
  description = "Subnets for the Fargate tasks. Need egress to grafana.com, the Grafana Cloud endpoints, and the AWS APIs."
  type        = list(string)
}

variable "assign_public_ip" {
  description = "Set true for public subnets with no NAT gateway."
  type        = bool
  default     = false
}

variable "schedules_enabled" {
  description = "Leave false for the first apply. See the comment in main.tf for the ordering that avoids a broken first run."
  type        = bool
  default     = false
}

variable "coverage_score_weights" {
  description = "Relative weights for metrics, logs, traces, profiles, dashboard, alert and SLO service completeness."
  type = object({
    metrics   = number
    logs      = number
    traces    = number
    profiles  = number
    dashboard = number
    alert     = number
    slo       = number
  })
  default = {
    metrics   = 1
    logs      = 1
    traces    = 1
    profiles  = 1
    dashboard = 1
    alert     = 1
    slo       = 1
  }
}

variable "firehose_logs_enabled" {
  description = "Create the optional ECS-log Firehose stream without yet wiring the live CloudWatch log group."
  type        = bool
  default     = false
}

variable "firehose_log_subscription_enabled" {
  description = "Connect the ECS log group only after a manual Firehose delivery has succeeded."
  type        = bool
  default     = false
}

variable "firehose_access_key_secret_arn" {
  description = "ARN of the adopted dedicated secret containing the Grafana Firehose access key in the api_key JSON field."
  type        = string
  default     = ""
}

variable "firehose_access_key_secret_kms_key_arn" {
  description = "Optional customer-managed KMS key ARN for the adopted Firehose access-key secret."
  type        = string
  default     = ""
}
