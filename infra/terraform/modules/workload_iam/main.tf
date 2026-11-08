# IRSA roles: one per ServiceAccount that the Helm chart creates. Each role trusts only its own
# ServiceAccount in the target namespace (sub + aud conditions).
#
# The ServiceAccount names are "<helm release name>-<component>". Keep helm_release_name in sync with
# the release name used by CD (`helm upgrade --install apex ...`).

locals {
  oidc_host = replace(var.oidc_issuer, "https://", "")
  components = {
    orchestrator   = "orchestrator"
    web            = "web"
    browser-worker = "browser-worker"
  }
}

data "aws_iam_policy_document" "trust" {
  for_each = local.components
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:sub"
      values   = ["system:serviceaccount:${var.namespace}:${var.helm_release_name}-${each.key}"]
    }
    condition {
      test     = "StringEquals"
      variable = "${local.oidc_host}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  for_each           = local.components
  name               = "${var.name_prefix}-${var.environment}-${each.key}"
  assume_role_policy = data.aws_iam_policy_document.trust[each.key].json
}

# Orchestrator: attachments and CSV read/write, audit trail append-only (no delete, no overwrite
# beyond what Object Lock allows), KMS for those buckets, and its own secret.
data "aws_iam_policy_document" "orchestrator" {
  statement {
    sid       = "ObjectsAttachmentsCsv"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [var.bucket_arns.attachments, "${var.bucket_arns.attachments}/*", var.bucket_arns.csv, "${var.bucket_arns.csv}/*"]
  }
  statement {
    sid       = "AuditAppendOnly"
    actions   = ["s3:PutObject", "s3:GetObject", "s3:ListBucket", "s3:GetBucketObjectLockConfiguration"]
    resources = [var.bucket_arns.audit, "${var.bucket_arns.audit}/*"]
  }
  statement {
    sid       = "Kms"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = var.kms_key_arns
  }
  statement {
    sid       = "OwnSecret"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [var.secret_arns["orchestrator"]]
  }
}

# Web (BFF): reads its own secret only (OIDC client settings). It never touches S3 or the database.
data "aws_iam_policy_document" "web" {
  statement {
    sid       = "OwnSecret"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [var.secret_arns["web"]]
  }
  statement {
    sid       = "Kms"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = [var.kms_key_arns[0]]
  }
}

# Browser worker: stores transcripts and screenshots in attachments (S3), its own secret.
data "aws_iam_policy_document" "browser_worker" {
  statement {
    sid       = "Attachments"
    actions   = ["s3:GetObject", "s3:PutObject", "s3:ListBucket"]
    resources = [var.bucket_arns.attachments, "${var.bucket_arns.attachments}/*"]
  }
  statement {
    sid       = "Kms"
    actions   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = [var.kms_key_arns[0]]
  }
  statement {
    sid       = "OwnSecret"
    actions   = ["secretsmanager:GetSecretValue", "secretsmanager:DescribeSecret"]
    resources = [var.secret_arns["browser-worker"]]
  }
}

resource "aws_iam_role_policy" "orchestrator" {
  name   = "orchestrator"
  role   = aws_iam_role.this["orchestrator"].id
  policy = data.aws_iam_policy_document.orchestrator.json
}

resource "aws_iam_role_policy" "web" {
  name   = "web"
  role   = aws_iam_role.this["web"].id
  policy = data.aws_iam_policy_document.web.json
}

resource "aws_iam_role_policy" "browser_worker" {
  name   = "browser-worker"
  role   = aws_iam_role.this["browser-worker"].id
  policy = data.aws_iam_policy_document.browser_worker.json
}
