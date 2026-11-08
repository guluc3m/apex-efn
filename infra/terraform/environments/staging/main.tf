data "aws_availability_zones" "available" {
  state = "available"
}

locals {
  name = "${var.name_prefix}-${var.environment}"
  azs  = slice(data.aws_availability_zones.available.names, 0, 3)
}

# ---------------------------------------------------------------------------
# Network (community module, pinned)
# ---------------------------------------------------------------------------

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.21.0"

  name = local.name
  cidr = var.vpc_cidr
  azs  = local.azs

  # /20 per AZ for private subnets, /24 per AZ for public (load balancers and NAT only).
  private_subnets = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 4, i)]
  public_subnets  = [for i, _ in local.azs : cidrsubnet(var.vpc_cidr, 8, 48 + i)]

  enable_nat_gateway     = true
  single_nat_gateway     = var.single_nat_gateway
  one_nat_gateway_per_az = !var.single_nat_gateway
  enable_dns_hostnames   = true
  enable_dns_support     = true

  public_subnet_tags = {
    "kubernetes.io/role/elb"              = "1"
    "kubernetes.io/cluster/${local.name}" = "shared"
  }

  private_subnet_tags = {
    "kubernetes.io/role/internal-elb"     = "1"
    "kubernetes.io/cluster/${local.name}" = "shared"
  }
}

# ---------------------------------------------------------------------------
# EKS (community module, pinned). Three managed node groups:
#   general: web, orchestrator, add-ons
#   browser: tainted, Chromium pods only (apex.io/nodepool=browser:NoSchedule)
#   gpu:     tainted, optional self-hosted LLM (count 0 by default)
# ---------------------------------------------------------------------------

module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.37.2"

  cluster_name    = local.name
  cluster_version = var.eks_cluster_version

  cluster_endpoint_public_access       = true
  cluster_endpoint_public_access_cidrs = var.eks_public_access_cidrs

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  authentication_mode                      = "API"
  enable_cluster_creator_admin_permissions = true
  enable_irsa                              = true

  # The CD role (GitHub OIDC) gets cluster admin only for the Helm deploy. Empty means no CD access.
  access_entries = var.deploy_role_arn == null ? {} : {
    cd = {
      principal_arn = var.deploy_role_arn
      policy_associations = {
        admin = {
          policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
          access_scope = { type = "cluster" }
        }
      }
    }
  }

  cluster_addons = {
    coredns    = {}
    kube-proxy = {}
    vpc-cni = {
      before_compute = true
    }
  }

  eks_managed_node_groups = {
    general = {
      instance_types = var.general_instance_types
      min_size       = var.general_min_size
      max_size       = var.general_max_size
      desired_size   = var.general_desired_size
      labels = {
        "apex.io/nodepool" = "general"
      }
    }

    browser = {
      instance_types = var.browser_instance_types
      min_size       = var.browser_min_size
      max_size       = var.browser_max_size
      desired_size   = var.browser_desired_size
      labels = {
        "apex.io/nodepool" = "browser"
      }
      taints = {
        dedicated = {
          key    = "apex.io/nodepool"
          value  = "browser"
          effect = "NO_SCHEDULE"
        }
      }
    }

    gpu = {
      ami_type       = "AL2023_x86_64_NVIDIA"
      instance_types = var.gpu_instance_types
      min_size       = 0
      max_size       = var.gpu_max_size
      desired_size   = var.gpu_node_count
      labels = {
        "apex.io/nodepool" = "gpu"
      }
      taints = {
        dedicated = {
          key    = "apex.io/nodepool"
          value  = "gpu"
          effect = "NO_SCHEDULE"
        }
      }
    }
  }
}

# ---------------------------------------------------------------------------
# Storage, data, and workload identity (local modules)
# ---------------------------------------------------------------------------

module "storage" {
  source = "../../modules/storage"

  name_prefix                      = var.name_prefix
  environment                      = var.environment
  audit_object_lock_retention_days = var.audit_object_lock_retention_days
}

module "data" {
  source = "../../modules/data"

  name_prefix            = var.name_prefix
  environment            = var.environment
  vpc_id                 = module.vpc.vpc_id
  private_subnet_ids     = module.vpc.private_subnets
  node_security_group_id = module.eks.node_security_group_id
  kms_key_arn            = module.storage.data_kms_key_arn

  rds_instance_class      = var.rds_instance_class
  rds_multi_az            = var.rds_multi_az
  rds_deletion_protection = var.rds_deletion_protection
  redis_node_type         = var.redis_node_type
  redis_multi_az          = var.redis_multi_az
}

module "workload_iam" {
  source = "../../modules/workload_iam"

  name_prefix       = var.name_prefix
  environment       = var.environment
  oidc_provider_arn = module.eks.oidc_provider_arn
  oidc_issuer       = module.eks.cluster_oidc_issuer_url
  namespace         = var.kubernetes_namespace
  helm_release_name = var.helm_release_name

  bucket_arns = {
    attachments = module.storage.attachments_bucket_arn
    csv         = module.storage.csv_bucket_arn
    audit       = module.storage.audit_bucket_arn
  }
  kms_key_arns = [module.storage.data_kms_key_arn, module.storage.audit_kms_key_arn]
  secret_arns  = module.data.secret_arns
}
