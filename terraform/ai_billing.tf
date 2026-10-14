# Policy only: existing narrowly scoped billing GETs, aggregate-only history.
variable "ai_billing_enabled" {
  description = "Enable aggregate-only observed AI monthly billing input and bounded dated history. No reader scope is added."
  type        = bool
  default     = false
}

variable "ai_personal_allowance" {
  description = "Personal tokens per org identity, deducted once across apps and stacks; stored with each observation."
  type        = number
  default     = 40000000
  validation {
    condition     = var.ai_personal_allowance >= 0 && var.ai_personal_allowance <= 9007199254740991 && floor(var.ai_personal_allowance) == var.ai_personal_allowance
    error_message = "AI personal allowance must be a nonnegative whole token count within the exact numeric bound."
  }
}

variable "ai_system_allowance" {
  description = "One shared org-wide system token allowance; stored with each observation."
  type        = number
  default     = 500000000
  validation {
    condition     = var.ai_system_allowance >= 0 && var.ai_system_allowance <= 9007199254740991 && floor(var.ai_system_allowance) == var.ai_system_allowance
    error_message = "AI system allowance must be a nonnegative whole token count within the exact numeric bound."
  }
}
