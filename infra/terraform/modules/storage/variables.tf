variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "apex"
}

variable "environment" {
  description = "Environment name (staging, production)."
  type        = string
}

variable "audit_object_lock_retention_days" {
  description = <<-EOT
    COMPLIANCE-mode Object Lock retention, in days, for the audit bucket.
    Default is 2190 days (6 years), the retention period for commercial books and records under
    Spanish Commercial Code art. 30 (ADR-900, issue #81). Once objects are written under COMPLIANCE
    mode the retention cannot be shortened, so the validation only allows lengthening it.
  EOT
  type        = number
  default     = 2190

  validation {
    condition     = var.audit_object_lock_retention_days >= 365
    error_message = "audit_object_lock_retention_days must be at least 365 days (1 year). The default is 2190 days (6 years, ADR-900 #81)."
  }
}

variable "kms_deletion_window_days" {
  description = "KMS key deletion window in days (7 to 30)."
  type        = number
  default     = 30

  validation {
    condition     = var.kms_deletion_window_days >= 7 && var.kms_deletion_window_days <= 30
    error_message = "kms_deletion_window_days must be between 7 and 30."
  }
}
