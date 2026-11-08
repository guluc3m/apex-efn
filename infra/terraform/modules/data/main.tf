locals {
  suffix = "${var.name_prefix}-${var.environment}"
}

# ---------------------------------------------------------------------------
# PostgreSQL 16 (pgvector is enabled per database with CREATE EXTENSION vector; no parameter needed)
# ---------------------------------------------------------------------------

resource "aws_db_subnet_group" "postgres" {
  name       = "${local.suffix}-postgres"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "postgres" {
  name        = "${local.suffix}-postgres"
  description = "PostgreSQL, reachable only from EKS nodes"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "postgres_from_nodes" {
  security_group_id            = aws_security_group.postgres.id
  referenced_security_group_id = var.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_db_parameter_group" "postgres" {
  name   = "${local.suffix}-postgres16"
  family = "postgres16"

  parameter {
    name  = "rds.force_ssl"
    value = "1"
  }
}

resource "aws_db_instance" "postgres" {
  identifier     = "${local.suffix}-postgres"
  engine         = "postgres"
  engine_version = var.rds_engine_version
  instance_class = var.rds_instance_class

  allocated_storage     = var.rds_allocated_storage_gb
  max_allocated_storage = var.rds_max_allocated_storage_gb
  storage_type          = "gp3"
  storage_encrypted     = true
  kms_key_id            = var.kms_key_arn

  db_name  = "apex"
  username = "apex_owner"
  # The master password is generated and kept by RDS in Secrets Manager, never in Terraform state.
  manage_master_user_password   = true
  master_user_secret_kms_key_id = var.kms_key_arn

  db_subnet_group_name   = aws_db_subnet_group.postgres.name
  vpc_security_group_ids = [aws_security_group.postgres.id]
  parameter_group_name   = aws_db_parameter_group.postgres.name
  publicly_accessible    = false

  multi_az                   = var.rds_multi_az
  backup_retention_period    = var.rds_backup_retention_days
  deletion_protection        = var.rds_deletion_protection
  auto_minor_version_upgrade = true
  copy_tags_to_snapshot      = true

  skip_final_snapshot       = false
  final_snapshot_identifier = "${local.suffix}-postgres-final"
}

# ---------------------------------------------------------------------------
# Redis (ElastiCache, TLS in transit, KMS at rest). Clients must use rediss://.
# ---------------------------------------------------------------------------

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.suffix}-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "redis" {
  name        = "${local.suffix}-redis"
  description = "Redis, reachable only from EKS nodes"
  vpc_id      = var.vpc_id
}

resource "aws_vpc_security_group_ingress_rule" "redis_from_nodes" {
  security_group_id            = aws_security_group.redis.id
  referenced_security_group_id = var.node_security_group_id
  ip_protocol                  = "tcp"
  from_port                    = 6379
  to_port                      = 6379
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id = "${local.suffix}-redis"
  description          = "APEX-EFN ${var.environment} Redis (queues, sessions, idempotency)"
  engine               = "redis"
  engine_version       = var.redis_engine_version
  node_type            = var.redis_node_type
  port                 = 6379

  num_cache_clusters         = var.redis_multi_az ? 2 : 1
  automatic_failover_enabled = var.redis_multi_az
  multi_az_enabled           = var.redis_multi_az

  subnet_group_name  = aws_elasticache_subnet_group.redis.name
  security_group_ids = [aws_security_group.redis.id]

  at_rest_encryption_enabled = true
  kms_key_id                 = var.kms_key_arn
  transit_encryption_enabled = true

  auto_minor_version_upgrade = true
  apply_immediately          = false
}

# ---------------------------------------------------------------------------
# Secrets Manager placeholders. Terraform creates the names and encryption only, never values.
# Values are written out of band (AWS console or CLI) and read by External Secrets Operator.
# ---------------------------------------------------------------------------

resource "aws_secretsmanager_secret" "app" {
  for_each = toset(var.secret_components)

  name                    = "${var.name_prefix}/${var.environment}/${each.key}"
  description             = "APEX-EFN ${var.environment} ${each.key} runtime configuration (values set out of band)"
  kms_key_id              = var.kms_key_arn
  recovery_window_in_days = 7
}
