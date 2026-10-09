# Policy only: no estate inventory, credential or new permission is introduced.
locals {
  label_catalogue = jsondecode(file("${path.module}/../collector/label_rules.json"))
  label_policy_rules = {
    for rule in local.label_catalogue.rules : rule.id => rule
    if rule.provenance != "published" && !contains([
      for band in values(lookup(local.label_catalogue.threshold_sources, rule.id, {})) : band.provenance
    ], "published")
  }
}

variable "loki_volume_enabled" {
  description = "Opt in to bounded 24h top100 Loki service_name volume, private input/S3 view only; total and remainder remain unknown."
  type        = bool
  default     = false
}

variable "rule_inventory_enabled" {
  description = "Opt in to count-only Mimir/Loki rules and current Alertmanager alert/silence states on witnessed GET routes."
  type        = bool
  default     = false
}

variable "label_inventory_enabled" {
  description = "Default-off bounded T2 label inventory; enabling does not grant permissions or customer rollout authority."
  type        = bool
  default     = false
}

variable "label_inventory_budget_seconds" {
  description = "Whole-second source caller-wait slice, additionally capped at a quarter of remaining T2 time. Not hard termination or a process-memory bound."
  type        = number
  default     = 900
  validation {
    condition     = var.label_inventory_budget_seconds > 0 && var.label_inventory_budget_seconds <= 900 && floor(var.label_inventory_budget_seconds) == var.label_inventory_budget_seconds
    error_message = "label_inventory_budget_seconds must be a positive whole number <=900."
  }
}

variable "label_inventory_static_names" {
  description = "Policy allowlist for the higher static-infrastructure cardinality band; unique label names only, not values or stack inventory."
  type        = list(string)
  default     = ["cluster", "host", "hostname", "k8s.cluster.name", "k8s.namespace.name", "k8s.node.name", "k8s_cluster_name", "k8s_namespace_name", "k8s_node_name", "namespace", "node"]
  validation {
    condition = length(var.label_inventory_static_names) <= 64 && length(distinct(var.label_inventory_static_names)) == length(var.label_inventory_static_names) && alltrue([
      for name in var.label_inventory_static_names : can(regex("^[A-Za-z_][A-Za-z0-9_.:-]{0,127}$", name))
    ])
    error_message = "label_inventory_static_names must contain <=64 unique, syntactically valid names of <=128 characters."
  }
}

variable "label_inventory_tunables" {
  description = "JSON evaluator policy: size_floor, static_multiplier, coverage_floor >=0.8, thresholds keyed by accepted catalogue rule. Published hard limits cannot be overridden; each override supplies all ordered positive bands. Defaults: 100, 10, 0.8, {}."
  type        = string
  default     = "{}"
  validation {
    condition = try(
      length(setsubtract(toset(keys(jsondecode(var.label_inventory_tunables))), toset(["size_floor", "static_multiplier", "coverage_floor", "thresholds"]))) == 0 &&
      can(regex("^[1-9][0-9]*$", jsonencode(lookup(jsondecode(var.label_inventory_tunables), "size_floor", 100)))) &&
      can(regex("^[1-9][0-9]*$", jsonencode(lookup(jsondecode(var.label_inventory_tunables), "static_multiplier", 10)))) &&
      can(regex("^(0[.][0-9]+|1([.]0+)?)$", jsonencode(lookup(jsondecode(var.label_inventory_tunables), "coverage_floor", 0.8)))) &&
      lookup(jsondecode(var.label_inventory_tunables), "coverage_floor", 0.8) >= 0.8 &&
      lookup(jsondecode(var.label_inventory_tunables), "coverage_floor", 0.8) <= 1 &&
      can(keys(lookup(jsondecode(var.label_inventory_tunables), "thresholds", {}))) &&
      alltrue([
        for id, bands in lookup(jsondecode(var.label_inventory_tunables), "thresholds", {}) :
        contains(keys(local.label_policy_rules), id) &&
        toset(keys(bands)) == toset(keys(local.label_policy_rules[id].thresholds)) &&
        alltrue([for value in values(bands) : can(regex("^[1-9][0-9]*$", jsonencode(value)))]) &&
        try(bands.warn < bands.high, true) && try(bands.high < bands.critical, true) && try(bands.warn < bands.critical, true)
      ]), false
    )
    error_message = "label_inventory_tunables must be valid JSON policy with positive whole floors, coverage in [0.8,1], and complete ordered positive bands for non-published catalogue rules only."
  }
}
