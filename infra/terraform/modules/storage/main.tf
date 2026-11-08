data "aws_caller_identity" "current" {}

locals {
  suffix = "${var.name_prefix}-${var.environment}"
}

# Two keys: one for operational data and CSVs, one dedicated to the audit trail, so that
# the audit key can be restricted to the audit writer without touching the rest.
resource "aws_kms_key" "data" {
  description             = "APEX-EFN ${var.environment}: attachments, CSV, secrets, RDS, Redis"
  enable_key_rotation     = true
  deletion_window_in_days = var.kms_deletion_window_days
}

resource "aws_kms_alias" "data" {
  name          = "alias/${local.suffix}-data"
  target_key_id = aws_kms_key.data.key_id
}

resource "aws_kms_key" "audit" {
  description             = "APEX-EFN ${var.environment}: signed audit log (S3 Object Lock)"
  enable_key_rotation     = true
  deletion_window_in_days = var.kms_deletion_window_days
}

resource "aws_kms_alias" "audit" {
  name          = "alias/${local.suffix}-audit"
  target_key_id = aws_kms_key.audit.key_id
}

module "attachments" {
  source      = "../secure_bucket"
  bucket_name = "${local.suffix}-attachments-${data.aws_caller_identity.current.account_id}"
  kms_key_arn = aws_kms_key.data.arn
}

module "csv" {
  source      = "../secure_bucket"
  bucket_name = "${local.suffix}-csv-${data.aws_caller_identity.current.account_id}"
  kms_key_arn = aws_kms_key.data.arn
}

# Audit log anchoring. Object Lock in COMPLIANCE mode: nobody, including root, can delete or shorten
# retention. The retention length is a TL decision (open question) and has no default on purpose.
module "audit" {
  source                     = "../secure_bucket"
  bucket_name                = "${local.suffix}-audit-${data.aws_caller_identity.current.account_id}"
  kms_key_arn                = aws_kms_key.audit.arn
  object_lock_retention_days = var.audit_object_lock_retention_days
}
