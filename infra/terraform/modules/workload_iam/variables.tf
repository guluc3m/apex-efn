variable "name_prefix" {
  description = "Resource name prefix."
  type        = string
  default     = "trato"
}

variable "environment" {
  description = "Environment name."
  type        = string
}

variable "oidc_provider_arn" {
  description = "ARN of the EKS cluster's IAM OIDC provider."
  type        = string
}

variable "oidc_issuer" {
  description = "Cluster OIDC issuer URL (https://oidc.eks...)."
  type        = string
}

variable "namespace" {
  description = "Kubernetes namespace the Helm release is installed in."
  type        = string
}

variable "helm_release_name" {
  description = "Helm release name. The ServiceAccount names are <release>-<component>."
  type        = string
  default     = "trato"
}

variable "bucket_arns" {
  description = "Bucket ARNs keyed by attachments, csv, audit."
  type = object({
    attachments = string
    csv         = string
    audit       = string
  })
}

variable "kms_key_arns" {
  description = "KMS key ARNs: [0] data key, [1] audit key."
  type        = list(string)
}

variable "secret_arns" {
  description = "Map component -> Secrets Manager ARN. Must contain orchestrator, web, browser-worker."
  type        = map(string)
}
