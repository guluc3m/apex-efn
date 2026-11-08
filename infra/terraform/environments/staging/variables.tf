variable "region" {
  description = "AWS region for staging. REQUIRED, no default: pick the region with the data-residency decision (EU data, GDPR)."
  type        = string
}

variable "environment" {
  description = "Environment name."
  type        = string
  default     = "staging"
}

variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "apex"
}

variable "vpc_cidr" {
  description = "VPC CIDR. Placeholder: must not overlap other networks you peer or connect to."
  type        = string
  default     = "10.40.0.0/16"
}

variable "single_nat_gateway" {
  description = "One shared NAT gateway (cheaper, not highly available). Acceptable for staging only."
  type        = bool
  default     = true
}

# ---- Audit (TL decision, no default on purpose) ---------------------------

variable "audit_object_lock_retention_days" {
  description = <<-EOT
    COMPLIANCE-mode Object Lock retention for the signed audit bucket, in days.
    REQUIRED, no default. Open Tech Lead question (tracked as issue #81). The spec does not define it,
    and it cannot be shortened once objects are written in COMPLIANCE mode.
  EOT
  type        = number
}

# ---- EKS -------------------------------------------------------------------

variable "eks_cluster_version" {
  description = "EKS Kubernetes version. Check the AWS support calendar before applying."
  type        = string
  default     = "1.34"
}

variable "eks_public_access_cidrs" {
  description = "CIDRs allowed to reach the public Kubernetes API endpoint. REQUIRED: no 0.0.0.0/0 default. Include the GitHub-hosted runner egress only if you accept it, or use a self-hosted runner in the VPC."
  type        = list(string)

  validation {
    condition     = length(var.eks_public_access_cidrs) > 0 && !contains(var.eks_public_access_cidrs, "0.0.0.0/0")
    error_message = "eks_public_access_cidrs must be non-empty and must not contain 0.0.0.0/0."
  }
}

variable "deploy_role_arn" {
  description = "ARN of the GitHub OIDC role used by .github/workflows/cd.yml (vars.AWS_DEPLOY_ROLE_ARN). null means no CD access entry."
  type        = string
  default     = null
}

variable "kubernetes_namespace" {
  description = "Namespace the Helm release is installed in. Must match the CD namespace."
  type        = string
  default     = "apex-staging"
}

variable "helm_release_name" {
  description = "Helm release name. Must match the release name used by CD (ServiceAccount names are <release>-<component>)."
  type        = string
  default     = "apex"
}

variable "general_instance_types" {
  description = "Instance types of the general node group. Staging placeholder."
  type        = list(string)
  default     = ["m6i.large"]
}

variable "general_min_size" {
  type    = number
  default = 2
}

variable "general_max_size" {
  type    = number
  default = 4
}

variable "general_desired_size" {
  type    = number
  default = 2
}

variable "browser_instance_types" {
  description = "Instance types of the browser node group (Chromium). Staging placeholder."
  type        = list(string)
  default     = ["c6i.xlarge"]
}

variable "browser_min_size" {
  type    = number
  default = 1
}

variable "browser_max_size" {
  type    = number
  default = 3
}

variable "browser_desired_size" {
  type    = number
  default = 1
}

variable "gpu_node_count" {
  description = "Desired GPU nodes for the optional self-hosted LLM. 0 disables the pool."
  type        = number
  default     = 0

  validation {
    condition     = var.gpu_node_count >= 0 && var.gpu_node_count <= var.gpu_max_size
    error_message = "gpu_node_count must be between 0 and gpu_max_size."
  }
}

variable "gpu_max_size" {
  type    = number
  default = 2
}

variable "gpu_instance_types" {
  description = "GPU instance types. Staging placeholder: size for the chosen model."
  type        = list(string)
  default     = ["g5.xlarge"]
}

# ---- Data -------------------------------------------------------------------

variable "rds_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "rds_multi_az" {
  type    = bool
  default = false
}

variable "rds_deletion_protection" {
  type    = bool
  default = true
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "redis_multi_az" {
  type    = bool
  default = false
}
