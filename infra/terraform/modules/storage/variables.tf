variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "trato"
}

variable "environment" {
  description = "Environment name (staging, production)."
  type        = string
}

variable "audit_object_lock_retention_days" {
  description = <<-EOT
    COMPLIANCE-mode Object Lock retention, in days, for the audit bucket.
    REQUIRED, no default. This is an open Tech Lead decision (open question, tracked as issue #81):
    the spec does not define the retention period, so it must not be invented here.
    Once objects are written under COMPLIANCE mode the retention cannot be shortened.
  EOT
  type        = number

  validation {
    condition     = var.audit_object_lock_retention_days >= 1
    error_message = "audit_object_lock_retention_days must be a positive number of days (TL decision, see variable description)."
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
