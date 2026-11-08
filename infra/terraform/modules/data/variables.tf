variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "trato"
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "vpc_id" {
  description = "VPC for the database and cache."
  type        = string
}

variable "private_subnet_ids" {
  description = "Private subnets for the DB and cache subnet groups."
  type        = list(string)
}

variable "node_security_group_id" {
  description = "EKS node security group. The only source allowed to reach PostgreSQL and Redis."
  type        = string
}

variable "kms_key_arn" {
  description = "Data KMS key ARN (storage module output)."
  type        = string
}

variable "secret_components" {
  description = "Components that get a Secrets Manager placeholder. Names become <prefix>/<env>/<component>."
  type        = list(string)
  default     = ["orchestrator", "web", "browser-worker", "llm"]
}

variable "rds_engine_version" {
  description = "PostgreSQL engine version. Must be a version RDS offers in the region (check `aws rds describe-db-engine-versions`)."
  type        = string
  default     = "16.6"
}

variable "rds_instance_class" {
  description = "RDS instance class. Staging placeholder: size it for real load."
  type        = string
  default     = "db.t4g.medium"
}

variable "rds_allocated_storage_gb" {
  description = "Initial storage in GiB."
  type        = number
  default     = 50
}

variable "rds_max_allocated_storage_gb" {
  description = "Storage autoscaling ceiling in GiB."
  type        = number
  default     = 200
}

variable "rds_multi_az" {
  description = "Multi-AZ standby. Off for staging."
  type        = bool
  default     = false
}

variable "rds_backup_retention_days" {
  description = "Automated backup retention in days."
  type        = number
  default     = 7
}

variable "rds_deletion_protection" {
  description = "Block deletion of the database instance."
  type        = bool
  default     = true
}

variable "redis_engine_version" {
  description = "Redis engine version."
  type        = string
  default     = "7.1"
}

variable "redis_node_type" {
  description = "ElastiCache node type. Staging placeholder."
  type        = string
  default     = "cache.t4g.small"
}

variable "redis_multi_az" {
  description = "Replica with automatic failover. Off for staging."
  type        = bool
  default     = false
}
