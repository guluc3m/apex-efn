#!/bin/sh
# Creates the dev buckets with Object Lock. Idempotent. Run by the `s3-init` service (aws-cli image).
set -eu
: "${S3_ENDPOINT:?S3_ENDPOINT not set}"
: "${S3_AUDIT_RETENTION_DAYS:=2192}"

s3api() { aws --endpoint-url "$S3_ENDPOINT" s3api "$@"; }

for b in apex-attachments apex-csv apex-audit; do
  s3api head-bucket --bucket "$b" 2>/dev/null || s3api create-bucket --bucket "$b" --object-lock-enabled-for-bucket >/dev/null
done

# Audit anchors cannot be deleted or shortened, not even by the root user, until they expire (ADR-211).
s3api put-object-lock-configuration --bucket apex-audit --object-lock-configuration \
  "{\"ObjectLockEnabled\":\"Enabled\",\"Rule\":{\"DefaultRetention\":{\"Mode\":\"COMPLIANCE\",\"Days\":$S3_AUDIT_RETENTION_DAYS}}}"

echo "apex buckets ready (audit retention=${S3_AUDIT_RETENTION_DAYS}d COMPLIANCE)"
