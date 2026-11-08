output "data_kms_key_arn" {
  description = "KMS key for attachments, CSV, secrets, RDS and Redis."
  value       = aws_kms_key.data.arn
}

output "audit_kms_key_arn" {
  description = "KMS key dedicated to the audit bucket."
  value       = aws_kms_key.audit.arn
}

output "attachments_bucket" {
  description = "Attachments bucket name (S3_BUCKET_ATTACHMENTS)."
  value       = module.attachments.id
}

output "attachments_bucket_arn" {
  description = "Attachments bucket ARN."
  value       = module.attachments.arn
}

output "csv_bucket" {
  description = "CSV bucket name (S3_BUCKET_CSV)."
  value       = module.csv.id
}

output "csv_bucket_arn" {
  description = "CSV bucket ARN."
  value       = module.csv.arn
}

output "audit_bucket" {
  description = "Audit bucket name (S3_BUCKET_AUDIT). Object Lock, COMPLIANCE mode."
  value       = module.audit.id
}

output "audit_bucket_arn" {
  description = "Audit bucket ARN."
  value       = module.audit.arn
}
