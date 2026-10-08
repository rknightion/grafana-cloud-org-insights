# Manifest mode: the module reads a consumer's decoded deployment manifest itself.
#
#   consumer_manifest = jsondecode(file("${path.module}/<name>.overlay.json"))
#
# Every module input a manifest key represents takes the manifest's value when the key is present and the
# module's own default when it is absent, so a consumer stops hand-copying glue and the manifest may omit
# any key whose value is the module default (`bin/consumer_manifest.py regenerate --prune-defaults`).
# The projection digests come from the manifest and explicit configuration is forced on.
#
# In manifest mode the module refuses at plan time (aws_ecs_cluster.this preconditions) an argument for a
# represented input that differs from its variable default; `bin/consumer_manifest.py check` also refuses
# one passed at exactly its default, which the module cannot see. Only the two kill switches,
# `schedules_enabled` and `provisioner_enabled`, stay as arguments, ANDed with the manifest. Inputs the manifest does not represent (image, subnet_ids, tiers sizing, tags, ...) remain
# ordinary arguments in both modes.
#
# `local.inputs` is a contract table: bin/consumer_manifest.py parses it to learn which manifest key feeds
# which module input, so keep each entry on one line in one of the three shapes used below.

variable "consumer_manifest" {
  description = "Decoded consumer deployment manifest (`jsondecode(file(...))`). Null keeps the explicit-argument interface. When set, the manifest supplies every input it represents, the runtime projection digests, and forces require_explicit_consumer_config."
  type        = any
  default     = null

  # Validations read var.consumer_manifest and plain variables, never local.inputs: that would form a cycle
  # through the variables it falls back to. Each manifest rule mirrors the validation of the input it feeds.
  validation {
    # Lives here rather than on each variable so variables.tf stays self-contained.
    condition = alltrue([
      for value in [var.name_prefix, var.grafana_org_id, var.write_stack_slug, var.mimir_write_url, var.mimir_tenant, var.loki_write_url, var.loki_tenant] :
      (value != null) != (var.consumer_manifest != null)
    ])
    error_message = "Without consumer_manifest, name_prefix, grafana_org_id, write_stack_slug, mimir_write_url, mimir_tenant, loki_write_url and loki_tenant are all required. With it, the manifest supplies them and each of these arguments must be left out."
  }

  validation {
    condition = var.consumer_manifest == null ? true : alltrue([
      can(keys(var.consumer_manifest.runtime.scan)),
      can(keys(var.consumer_manifest.runtime.provisioner)),
      can(keys(var.consumer_manifest.aws)),
      can(regex("^[0-9a-f]{64}$", var.consumer_manifest.runtime_projection_digests.scan)),
      can(regex("^[0-9a-f]{64}$", var.consumer_manifest.runtime_projection_digests.provisioner)),
    ])
    error_message = "consumer_manifest must be a decoded deployment manifest with runtime.scan, runtime.provisioner, aws and 64-hex runtime_projection_digests.scan and .provisioner."
  }

  validation {
    condition = var.consumer_manifest == null ? true : alltrue(flatten([
      for section, names in local.manifest_required_keys : [
        for name in names : can(try(var.consumer_manifest.runtime[section], var.consumer_manifest[section])[name])
      ]
    ]))
    error_message = "consumer_manifest omits a key that has no module default. Run `bin/consumer_manifest.py check` for the key names."
  }

  validation {
    # A key both projections carry is read once, from runtime.scan, so the two must agree.
    condition = var.consumer_manifest == null ? true : alltrue([
      for name in local.manifest_shared_keys :
      try(var.consumer_manifest.runtime.scan[name], null) == try(var.consumer_manifest.runtime.provisioner[name], null)
    ])
    error_message = "consumer_manifest runtime.scan and runtime.provisioner must carry identical values for every key they share, and omit such a key from both or neither."
  }

  validation {
    condition = var.consumer_manifest == null ? true : alltrue([
      can(regex("^[a-z0-9][a-z0-9-]{1,26}[a-z0-9]$", try(var.consumer_manifest.aws.name_prefix, "aaa"))),
      startswith(try(var.consumer_manifest.runtime.scan.GCINSIGHT_MIMIR_URL, "https://"), "https://"),
      can(regex("^https://[A-Za-z0-9.-]+/?$", try(var.consumer_manifest.runtime.scan.GCINSIGHT_LOKI_URL, "https://a"))),
      contains(["ARM64", "X86_64"], try(var.consumer_manifest.aws.task_architecture, "ARM64")),
    ])
    error_message = "consumer_manifest has an invalid aws.name_prefix, GCINSIGHT_MIMIR_URL, GCINSIGHT_LOKI_URL or aws.task_architecture (the rules of the name_prefix, mimir_write_url, loki_write_url and task_architecture inputs)."
  }

  validation {
    condition = var.consumer_manifest == null ? true : alltrue([
      startswith(try(var.consumer_manifest.runtime.scan.GCINSIGHT_STACK_TOKEN_PREFIX, "/a"), "/") && !endswith(try(var.consumer_manifest.runtime.scan.GCINSIGHT_STACK_TOKEN_PREFIX, "/a"), "/"),
      can(regex("^[a-z][a-z0-9_.-]*$", try(var.consumer_manifest.runtime.scan.GCINSIGHT_METRIC_PREFIX, "a"))),
      can(regex("^([0-9]+([.][0-9]+)?(ms|s|m|h))+$", try(var.consumer_manifest.runtime.scan.GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL, "60s"))) && !can(regex("^([0.]+(ms|s|m|h))+$", try(var.consumer_manifest.runtime.scan.GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL, "60s"))),
      contains(["0", "1"], try(var.consumer_manifest.runtime.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED, "0")),
      contains(["0", "1"], try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_ENABLED, "0")),
    ])
    error_message = "consumer_manifest has an invalid GCINSIGHT_STACK_TOKEN_PREFIX, GCINSIGHT_METRIC_PREFIX or GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL (the rules of the matching inputs), or a GCINSIGHT_*_ENABLED flag other than 1 or 0."
  }

  validation {
    condition = var.consumer_manifest == null ? true : try(
      length(distinct(compact(split(",", try(var.consumer_manifest.runtime.scan.GCINSIGHT_READER_PRODUCT_READS, ""))))) == length(compact(split(",", try(var.consumer_manifest.runtime.scan.GCINSIGHT_READER_PRODUCT_READS, "")))) && alltrue([
        for family in compact(split(",", try(var.consumer_manifest.runtime.scan.GCINSIGHT_READER_PRODUCT_READS, ""))) : contains(["slo", "synthetic-monitoring", "synthetic-monitoring-query", "irm-integrations", "irm-alert-groups", "faro-apps", "ml-jobs", "cloud-accounts", "pdc-networks", "reports", "playlists", "library-panels"], family)
      ]) && (!contains(compact(split(",", try(var.consumer_manifest.runtime.scan.GCINSIGHT_READER_PRODUCT_READS, ""))), "synthetic-monitoring-query") || contains(compact(split(",", try(var.consumer_manifest.runtime.scan.GCINSIGHT_READER_PRODUCT_READS, ""))), "synthetic-monitoring")),
      false,
    )
    error_message = "consumer_manifest GCINSIGHT_READER_PRODUCT_READS must follow the provisioner_product_reads rule: unique known product families, and synthetic-monitoring-query requires synthetic-monitoring."
  }

  validation {
    condition = var.consumer_manifest == null ? true : try(
      alltrue([for weight in values(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_COVERAGE_SCORE_WEIGHTS, "{\"metrics\":1}"))) : weight >= 0]) &&
      sum(values(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_COVERAGE_SCORE_WEIGHTS, "{\"metrics\":1}")))) > 0 &&
      alltrue([
        for policy in jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_EXPECTED_RETENTION_POLICY, "[]")) :
        trimspace(policy.selector) != "" && can(regex("^[0-9]+([.][0-9]+)?[dh]$", trimspace(policy.minimum_period)))
      ]),
      false,
    )
    error_message = "consumer_manifest GCINSIGHT_COVERAGE_SCORE_WEIGHTS or GCINSIGHT_EXPECTED_RETENTION_POLICY breaks the coverage_score_weights or expected_retention_policy rule."
  }

  validation {
    condition = var.consumer_manifest == null ? true : try(
      tonumber(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS, "900")) > 0 &&
      tonumber(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS, "900")) <= 900 &&
      floor(tonumber(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS, "900"))) == tonumber(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS, "900")) &&
      length(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES, "[]"))) <= 64 &&
      length(distinct(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES, "[]")))) == length(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES, "[]"))) &&
      alltrue([for name in jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES, "[]")) : can(regex("^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$", name))]),
      false,
    )
    error_message = "consumer_manifest GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS or GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES breaks the label_inventory_budget_seconds or label_inventory_static_names rule."
  }

  validation {
    # The label_inventory_tunables rule, applied to the manifest's string.
    condition = var.consumer_manifest == null ? true : try(
      length(setsubtract(toset(keys(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")))), toset(["size_floor", "static_multiplier", "coverage_floor", "thresholds"]))) == 0 &&
      can(regex("^[1-9][0-9]*$", jsonencode(lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "size_floor", 100)))) &&
      can(regex("^[1-9][0-9]*$", jsonencode(lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "static_multiplier", 10)))) &&
      can(regex("^(0[.][0-9]+|1([.]0+)?)$", jsonencode(lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "coverage_floor", 0.8)))) &&
      lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "coverage_floor", 0.8) >= 0.8 &&
      lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "coverage_floor", 0.8) <= 1 &&
      can(keys(lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "thresholds", {}))) &&
      alltrue([
        for id, bands in lookup(jsondecode(try(var.consumer_manifest.runtime.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES, "{}")), "thresholds", {}) :
        contains(keys(local.label_policy_rules), id) &&
        toset(keys(bands)) == toset(keys(local.label_policy_rules[id].thresholds)) &&
        alltrue([for value in values(bands) : can(regex("^[1-9][0-9]*$", jsonencode(value)))]) &&
        try(bands.warn < bands.high, true) && try(bands.high < bands.critical, true) && try(bands.warn < bands.critical, true)
      ]), false
    )
    error_message = "consumer_manifest GCINSIGHT_LABEL_INVENTORY_TUNABLES breaks the label_inventory_tunables rule."
  }
}

locals {
  manifest_mode = var.consumer_manifest != null

  # `try` rather than a conditional: an object and `{}` have no common type for a conditional to unify.
  manifest = {
    scan        = try(var.consumer_manifest.runtime.scan, {})
    provisioner = try(var.consumer_manifest.runtime.provisioner, {})
    aws         = try(var.consumer_manifest.aws, {})
  }
  manifest_keys = { for section, values in local.manifest : section => keys(values) }

  # Keys with no module default. bin/consumer_manifest.py re-derives this set from the module defaults and
  # a test fails if the two disagree. Literal, so the consumer_manifest validation can read it.
  manifest_required_keys = {
    scan = [
      "GCINSIGHT_ORG_ID", "GCINSIGHT_WRITE_STACK", "GCINSIGHT_MIMIR_URL", "GCINSIGHT_MIMIR_TENANT",
      "GCINSIGHT_LOKI_URL", "GCINSIGHT_LOKI_TENANT", "GCINSIGHT_S3_BUCKET", "GCINSIGHT_S3_REGION",
      "GCINSIGHT_SSM_REGION",
    ]
    provisioner = ["GCINSIGHT_ORG_ID", "GCINSIGHT_SSM_REGION"]
    aws         = ["name_prefix", "cost_namespace", "purpose_tag"]
  }
  manifest_shared_keys = [
    "GCINSIGHT_ORG_ID", "GCINSIGHT_SSM_REGION", "GCINSIGHT_STACK_TOKEN_PREFIX", "GCINSIGHT_OPT_OUT",
    "GCINSIGHT_READER_PRODUCT_READS",
  ]

  coverage_weight_names = ["metrics", "logs", "traces", "profiles", "dashboard", "alert", "slo"]

  # The effective value of every manifest-represented input. In explicit mode every entry is exactly the
  # variable of the same name. Conversions mirror the variable's type, as the explicit consumer glue did.
  inputs = {
    name_prefix                       = contains(local.manifest_keys.aws, "name_prefix") ? tostring(local.manifest.aws.name_prefix) : var.name_prefix
    bucket_name                       = contains(local.manifest_keys.aws, "bucket_name") ? tostring(local.manifest.aws.bucket_name) : var.bucket_name
    secret_name                       = contains(local.manifest_keys.aws, "secret_name") ? tostring(local.manifest.aws.secret_name) : var.secret_name
    reader_secret_key                 = contains(local.manifest_keys.aws, "reader_secret_key") ? tostring(local.manifest.aws.reader_secret_key) : var.reader_secret_key
    writer_secret_key                 = contains(local.manifest_keys.aws, "writer_secret_key") ? tostring(local.manifest.aws.writer_secret_key) : var.writer_secret_key
    provisioner_secret_key            = contains(local.manifest_keys.aws, "provisioner_secret_key") ? tostring(local.manifest.aws.provisioner_secret_key) : var.provisioner_secret_key
    create_bucket                     = contains(local.manifest_keys.aws, "create_bucket") ? tobool(local.manifest.aws.create_bucket) : var.create_bucket
    create_secret                     = contains(local.manifest_keys.aws, "create_secret") ? tobool(local.manifest.aws.create_secret) : var.create_secret
    create_views_reader_user          = contains(local.manifest_keys.aws, "create_views_reader_user") ? tobool(local.manifest.aws.create_views_reader_user) : var.create_views_reader_user
    create_provisioner                = contains(local.manifest_keys.aws, "create_provisioner") ? tobool(local.manifest.aws.create_provisioner) : var.create_provisioner
    firehose_logs_enabled             = contains(local.manifest_keys.aws, "firehose_logs_enabled") ? tobool(local.manifest.aws.firehose_logs_enabled) : var.firehose_logs_enabled
    firehose_log_subscription_enabled = contains(local.manifest_keys.aws, "firehose_log_subscription_enabled") ? tobool(local.manifest.aws.firehose_log_subscription_enabled) : var.firehose_log_subscription_enabled
    assign_public_ip                  = contains(local.manifest_keys.aws, "assign_public_ip") ? tobool(local.manifest.aws.assign_public_ip) : var.assign_public_ip
    schedule_timezone                 = contains(local.manifest_keys.aws, "schedule_timezone") ? tostring(local.manifest.aws.schedule_timezone) : var.schedule_timezone
    provisioner_schedule_expression   = contains(local.manifest_keys.aws, "provisioner_schedule") ? tostring(local.manifest.aws.provisioner_schedule) : var.provisioner_schedule_expression
    task_architecture                 = contains(local.manifest_keys.aws, "task_architecture") ? tostring(local.manifest.aws.task_architecture) : var.task_architecture
    manage_adopted_bucket_config      = contains(local.manifest_keys.aws, "manage_adopted_bucket_config") ? tobool(local.manifest.aws.manage_adopted_bucket_config) : var.manage_adopted_bucket_config

    grafana_org_id                 = contains(local.manifest_keys.scan, "GCINSIGHT_ORG_ID") ? tostring(local.manifest.scan.GCINSIGHT_ORG_ID) : var.grafana_org_id
    write_stack_slug               = contains(local.manifest_keys.scan, "GCINSIGHT_WRITE_STACK") ? tostring(local.manifest.scan.GCINSIGHT_WRITE_STACK) : var.write_stack_slug
    mimir_write_url                = contains(local.manifest_keys.scan, "GCINSIGHT_MIMIR_URL") ? tostring(local.manifest.scan.GCINSIGHT_MIMIR_URL) : var.mimir_write_url
    mimir_tenant                   = contains(local.manifest_keys.scan, "GCINSIGHT_MIMIR_TENANT") ? tostring(local.manifest.scan.GCINSIGHT_MIMIR_TENANT) : var.mimir_tenant
    loki_write_url                 = contains(local.manifest_keys.scan, "GCINSIGHT_LOKI_URL") ? tostring(local.manifest.scan.GCINSIGHT_LOKI_URL) : var.loki_write_url
    loki_tenant                    = contains(local.manifest_keys.scan, "GCINSIGHT_LOKI_TENANT") ? tostring(local.manifest.scan.GCINSIGHT_LOKI_TENANT) : var.loki_tenant
    stack_token_prefix             = contains(local.manifest_keys.scan, "GCINSIGHT_STACK_TOKEN_PREFIX") ? tostring(local.manifest.scan.GCINSIGHT_STACK_TOKEN_PREFIX) : var.stack_token_prefix
    metric_prefix                  = contains(local.manifest_keys.scan, "GCINSIGHT_METRIC_PREFIX") ? tostring(local.manifest.scan.GCINSIGHT_METRIC_PREFIX) : var.metric_prefix
    loki_job                       = contains(local.manifest_keys.scan, "GCINSIGHT_LOKI_JOB") ? tostring(local.manifest.scan.GCINSIGHT_LOKI_JOB) : var.loki_job
    collector_user_agent           = contains(local.manifest_keys.scan, "GCINSIGHT_USER_AGENT") ? tostring(local.manifest.scan.GCINSIGHT_USER_AGENT) : var.collector_user_agent
    provision_opt_out              = contains(local.manifest_keys.scan, "GCINSIGHT_OPT_OUT") ? compact(split(",", tostring(local.manifest.scan.GCINSIGHT_OPT_OUT))) : var.provision_opt_out
    provisioner_product_reads      = contains(local.manifest_keys.scan, "GCINSIGHT_READER_PRODUCT_READS") ? compact(split(",", tostring(local.manifest.scan.GCINSIGHT_READER_PRODUCT_READS))) : var.provisioner_product_reads
    coverage_score_weights         = contains(local.manifest_keys.scan, "GCINSIGHT_COVERAGE_SCORE_WEIGHTS") ? { for name in local.coverage_weight_names : name => tonumber(jsondecode(local.manifest.scan.GCINSIGHT_COVERAGE_SCORE_WEIGHTS)[name]) } : var.coverage_score_weights
    dashboard_detail_enabled       = contains(local.manifest_keys.scan, "GCINSIGHT_DASHBOARD_DETAIL_ENABLED") ? local.manifest.scan.GCINSIGHT_DASHBOARD_DETAIL_ENABLED == "1" : var.dashboard_detail_enabled
    expected_retention_policy      = contains(local.manifest_keys.scan, "GCINSIGHT_EXPECTED_RETENTION_POLICY") ? [for policy in jsondecode(local.manifest.scan.GCINSIGHT_EXPECTED_RETENTION_POLICY) : { selector = tostring(policy.selector), minimum_period = tostring(policy.minimum_period) }] : var.expected_retention_policy
    fleet_default_scrape_interval  = contains(local.manifest_keys.scan, "GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL") ? tostring(local.manifest.scan.GCINSIGHT_FLEET_DEFAULT_SCRAPE_INTERVAL) : var.fleet_default_scrape_interval
    label_inventory_enabled        = contains(local.manifest_keys.scan, "GCINSIGHT_LABEL_INVENTORY_ENABLED") ? local.manifest.scan.GCINSIGHT_LABEL_INVENTORY_ENABLED == "1" : var.label_inventory_enabled
    label_inventory_tunables       = contains(local.manifest_keys.scan, "GCINSIGHT_LABEL_INVENTORY_TUNABLES") ? tostring(local.manifest.scan.GCINSIGHT_LABEL_INVENTORY_TUNABLES) : var.label_inventory_tunables
    label_inventory_static_names   = contains(local.manifest_keys.scan, "GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES") ? [for name in jsondecode(local.manifest.scan.GCINSIGHT_LABEL_INVENTORY_STATIC_NAMES) : tostring(name)] : var.label_inventory_static_names
    label_inventory_budget_seconds = contains(local.manifest_keys.scan, "GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS") ? tonumber(local.manifest.scan.GCINSIGHT_LABEL_INVENTORY_BUDGET_SECONDS) : var.label_inventory_budget_seconds

    role_name                   = contains(local.manifest_keys.provisioner, "GCINSIGHT_ROLE_NAME") ? tostring(local.manifest.provisioner.GCINSIGHT_ROLE_NAME) : var.role_name
    role_display                = contains(local.manifest_keys.provisioner, "GCINSIGHT_ROLE_DISPLAY") ? tostring(local.manifest.provisioner.GCINSIGHT_ROLE_DISPLAY) : var.role_display
    role_group                  = contains(local.manifest_keys.provisioner, "GCINSIGHT_ROLE_GROUP") ? tostring(local.manifest.provisioner.GCINSIGHT_ROLE_GROUP) : var.role_group
    reader_service_account_name = contains(local.manifest_keys.provisioner, "GCINSIGHT_READER_SA_NAME") ? tostring(local.manifest.provisioner.GCINSIGHT_READER_SA_NAME) : var.reader_service_account_name
    admin_service_account_name  = contains(local.manifest_keys.provisioner, "GCINSIGHT_ADMIN_SA_NAME") ? tostring(local.manifest.provisioner.GCINSIGHT_ADMIN_SA_NAME) : var.admin_service_account_name
    token_name_prefix           = contains(local.manifest_keys.provisioner, "GCINSIGHT_TOKEN_NAME_PREFIX") ? tostring(local.manifest.provisioner.GCINSIGHT_TOKEN_NAME_PREFIX) : var.token_name_prefix

    # Rendered by the module itself in manifest mode.
    scan_runtime_config_digest        = local.manifest_mode ? tostring(var.consumer_manifest.runtime_projection_digests.scan) : var.scan_runtime_config_digest
    provisioner_runtime_config_digest = local.manifest_mode ? tostring(var.consumer_manifest.runtime_projection_digests.provisioner) : var.provisioner_runtime_config_digest
    require_explicit_consumer_config  = local.manifest_mode ? true : var.require_explicit_consumer_config

    # Kill switches: still arguments in manifest mode, ANDed with the manifest's value.
    schedules_enabled   = var.schedules_enabled && (contains(local.manifest_keys.aws, "schedules_enabled") ? tobool(local.manifest.aws.schedules_enabled) : true)
    provisioner_enabled = var.provisioner_enabled && (contains(local.manifest_keys.aws, "provisioner_enabled") ? tobool(local.manifest.aws.provisioner_enabled) : true)
  }

  # The manifest's two tag values, applied OVER the caller's `tags` in manifest mode only: the manifest
  # wins a key clash, exactly as the consumers' own `merge(var.tags, {Purpose, Namespace})` did. Explicit
  # mode applies `tags` alone, as before.
  manifest_tags = local.manifest_mode ? {
    Purpose   = tostring(local.manifest.aws.purpose_tag)
    Namespace = tostring(local.manifest.aws.cost_namespace)
  } : {}

  # Plan-time refusal of explicit arguments beside a manifest. Every represented input except the two
  # kill switches, as passed, and its variable default; the module cannot tell an argument equal to its
  # default from an omitted one, so only a differing argument is refused. A tofu test holds the key set
  # equal to local.inputs and the defaults equal to the variable declarations; a pytest holds each entry
  # reading the variable of its own name.
  input_arguments = {
    name_prefix                       = var.name_prefix
    bucket_name                       = var.bucket_name
    secret_name                       = var.secret_name
    reader_secret_key                 = var.reader_secret_key
    writer_secret_key                 = var.writer_secret_key
    provisioner_secret_key            = var.provisioner_secret_key
    create_bucket                     = var.create_bucket
    create_secret                     = var.create_secret
    create_views_reader_user          = var.create_views_reader_user
    create_provisioner                = var.create_provisioner
    firehose_logs_enabled             = var.firehose_logs_enabled
    firehose_log_subscription_enabled = var.firehose_log_subscription_enabled
    assign_public_ip                  = var.assign_public_ip
    schedule_timezone                 = var.schedule_timezone
    provisioner_schedule_expression   = var.provisioner_schedule_expression
    task_architecture                 = var.task_architecture
    manage_adopted_bucket_config      = var.manage_adopted_bucket_config
    grafana_org_id                    = var.grafana_org_id
    write_stack_slug                  = var.write_stack_slug
    mimir_write_url                   = var.mimir_write_url
    mimir_tenant                      = var.mimir_tenant
    loki_write_url                    = var.loki_write_url
    loki_tenant                       = var.loki_tenant
    stack_token_prefix                = var.stack_token_prefix
    metric_prefix                     = var.metric_prefix
    loki_job                          = var.loki_job
    collector_user_agent              = var.collector_user_agent
    provision_opt_out                 = var.provision_opt_out
    provisioner_product_reads         = var.provisioner_product_reads
    coverage_score_weights            = var.coverage_score_weights
    dashboard_detail_enabled          = var.dashboard_detail_enabled
    expected_retention_policy         = var.expected_retention_policy
    fleet_default_scrape_interval     = var.fleet_default_scrape_interval
    label_inventory_enabled           = var.label_inventory_enabled
    label_inventory_tunables          = var.label_inventory_tunables
    label_inventory_static_names      = var.label_inventory_static_names
    label_inventory_budget_seconds    = var.label_inventory_budget_seconds
    role_name                         = var.role_name
    role_display                      = var.role_display
    role_group                        = var.role_group
    reader_service_account_name       = var.reader_service_account_name
    admin_service_account_name        = var.admin_service_account_name
    token_name_prefix                 = var.token_name_prefix
    scan_runtime_config_digest        = var.scan_runtime_config_digest
    provisioner_runtime_config_digest = var.provisioner_runtime_config_digest
    require_explicit_consumer_config  = var.require_explicit_consumer_config
  }
  input_defaults = {
    name_prefix                       = null
    bucket_name                       = ""
    secret_name                       = ""
    reader_secret_key                 = "GCINSIGHT_READ_TOKEN"
    writer_secret_key                 = "GCINSIGHT_WRITE_TOKEN"
    provisioner_secret_key            = "GCINSIGHT_PROVISION_TOKEN"
    create_bucket                     = true
    create_secret                     = true
    create_views_reader_user          = true
    create_provisioner                = false
    firehose_logs_enabled             = false
    firehose_log_subscription_enabled = false
    assign_public_ip                  = false
    schedule_timezone                 = "UTC"
    provisioner_schedule_expression   = "cron(15 3 * * ? *)"
    task_architecture                 = "ARM64"
    manage_adopted_bucket_config      = false
    grafana_org_id                    = null
    write_stack_slug                  = null
    mimir_write_url                   = null
    mimir_tenant                      = null
    loki_write_url                    = null
    loki_tenant                       = null
    stack_token_prefix                = "/gcinsight/stack-token"
    metric_prefix                     = "gcinsight"
    loki_job                          = "gcinsight"
    collector_user_agent              = "gcinsight-collector/1 (+grafana-ps)"
    provision_opt_out                 = []
    provisioner_product_reads         = []
    coverage_score_weights            = { metrics = 1, logs = 1, traces = 1, profiles = 1, dashboard = 1, alert = 1, slo = 1 }
    dashboard_detail_enabled          = false
    expected_retention_policy         = []
    fleet_default_scrape_interval     = "60s"
    label_inventory_enabled           = false
    label_inventory_tunables          = "{}"
    label_inventory_static_names      = ["cluster", "host", "hostname", "k8s.cluster.name", "k8s.namespace.name", "k8s.node.name", "k8s_cluster_name", "k8s_namespace_name", "k8s_node_name", "namespace", "node"]
    label_inventory_budget_seconds    = 900
    role_name                         = "custom:gcinsight.reader"
    role_display                      = "Grafana Cloud Org Insights reader"
    role_group                        = "Grafana Cloud Org Insights"
    reader_service_account_name       = "gcinsight-data"
    admin_service_account_name        = "gcinsight-insights-provisioner"
    token_name_prefix                 = "gcinsight-data"
    scan_runtime_config_digest        = ""
    provisioner_runtime_config_digest = ""
    require_explicit_consumer_config  = false
  }
  explicit_input_arguments = sort([
    for name, value in local.input_arguments : name if jsonencode(value) != jsonencode(local.input_defaults[name])
  ])

  # Manifest tier schedules naming a tier the caller's `tiers` does not declare.
  manifest_schedule_orphans = sort([
    for key in local.manifest_keys.aws : key
    if can(regex("^t[0-9]+_schedule$", key)) && !contains(keys(var.tiers), trimsuffix(key, "_schedule"))
  ])
  # Tier entries carrying a schedule_expression other than the module default in manifest mode.
  explicit_tier_schedules = sort([
    for name, cfg in var.tiers : name
    if cfg.schedule_expression != null && cfg.schedule_expression != lookup(local.default_tier_schedules, name, null)
  ])

  # Module default cadence per tier, interpreted in schedule_timezone, for a tier entry that omits
  # schedule_expression; in manifest mode the aws.<tier>_schedule key overrides it. It repeats the tiers
  # variable's defaults, which a test holds equal. bin/consumer_manifest.py reads this map as the default
  # of those keys. RUNBOOK.md holds the canonical operator timetable.
  default_tier_schedules = {
    t1 = "cron(5 * * * ? *)"          # hourly at :05
    t2 = "cron(30 3 * * ? *)"         # daily, after the 03:15 provisioner
    t3 = "cron(40 2,8,14,20 * * ? *)" # six-hourly
    t4 = "cron(0 9 * * ? *)"          # daily, well after the 02:40 T3
  }

  tiers = {
    for name, cfg in var.tiers : name => merge(cfg, {
      schedule_expression = contains(local.manifest_keys.aws, "${name}_schedule") ? tostring(local.manifest.aws["${name}_schedule"]) : (
        cfg.schedule_expression != null ? cfg.schedule_expression : lookup(local.default_tier_schedules, name, null)
      )
    })
  }
}
