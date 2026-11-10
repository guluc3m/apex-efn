variable "bucket_name" {
  description = "Globally unique bucket name."
  type        = string
}

variable "kms_key_arn" {
  description = "KMS key used for SSE-KMS on this bucket."
  type        = string
}

variable "object_lock_retention_days" {
  description = "Default COMPLIANCE-mode retention in days. null disables Object Lock. Only the audit bucket sets this."
  type        = number
  default     = null
  nullable    = true

  validation {
    condition     = var.object_lock_retention_days == null ? true : var.object_lock_retention_days >= 1
    error_message = "object_lock_retention_days must be null or at least 1."
  }
}
