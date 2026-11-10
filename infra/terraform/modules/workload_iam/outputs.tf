output "role_arns" {
  description = "IRSA role ARN per component. Feed them to the Helm serviceAccount annotations (eks.amazonaws.com/role-arn)."
  value       = { for k, r in aws_iam_role.this : k => r.arn }
}
