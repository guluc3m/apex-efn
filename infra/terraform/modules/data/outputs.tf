output "postgres_endpoint" {
  description = "RDS endpoint (host:port). Build DATABASE_URL from it plus the RDS-managed secret."
  value       = aws_db_instance.postgres.endpoint
}

output "postgres_master_user_secret_arn" {
  description = "Secrets Manager ARN of the RDS-managed master credentials."
  value       = aws_db_instance.postgres.master_user_secret[0].secret_arn
}

output "redis_primary_endpoint" {
  description = "Redis primary endpoint. Use rediss:// (TLS)."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "secret_arns" {
  description = "Map component -> Secrets Manager ARN (placeholders, values set out of band)."
  value       = { for k, s in aws_secretsmanager_secret.app : k => s.arn }
}

output "secret_names" {
  description = "Map component -> Secrets Manager name, matching the External Secrets remoteKey convention."
  value       = { for k, s in aws_secretsmanager_secret.app : k => s.name }
}
