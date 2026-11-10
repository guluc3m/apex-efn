output "cluster_name" {
  description = "EKS cluster name (vars.EKS_CLUSTER_NAME in GitHub)."
  value       = module.eks.cluster_name
}

output "cluster_endpoint" {
  description = "Kubernetes API endpoint."
  value       = module.eks.cluster_endpoint
}

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "postgres_endpoint" {
  value = module.data.postgres_endpoint
}

output "postgres_master_user_secret_arn" {
  description = "RDS-managed master credentials. Build DATABASE_URL for the app roles from this, out of band."
  value       = module.data.postgres_master_user_secret_arn
}

output "redis_primary_endpoint" {
  value = module.data.redis_primary_endpoint
}

output "attachments_bucket" {
  description = "Value for config.S3_BUCKET_ATTACHMENTS."
  value       = module.storage.attachments_bucket
}

output "csv_bucket" {
  description = "Value for config.S3_BUCKET_CSV."
  value       = module.storage.csv_bucket
}

output "audit_bucket" {
  description = "Value for config.S3_BUCKET_AUDIT."
  value       = module.storage.audit_bucket
}

output "irsa_role_arns" {
  description = "Values for <component>.serviceAccount.annotations[eks.amazonaws.com/role-arn] in Helm."
  value       = module.workload_iam.role_arns
}

output "secret_names" {
  description = "Secrets Manager names (External Secrets remoteKey values). Values are set out of band."
  value       = module.data.secret_names
}
