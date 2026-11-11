#!/bin/sh
# Create the development buckets. Idempotent: safe to run again.
# Run by the `rustfs-init` one-shot service in infra/docker-compose.yml.
set -eu

: "${RUSTFS_ENDPOINT:?RUSTFS_ENDPOINT is not set}"
: "${AWS_ACCESS_KEY_ID:?AWS_ACCESS_KEY_ID is not set}"
: "${AWS_SECRET_ACCESS_KEY:?AWS_SECRET_ACCESS_KEY is not set}"
: "${AWS_DEFAULT_REGION:=us-east-1}"
# DEV ONLY. Production retention (COMPLIANCE mode) is a TL decision.
: "${RUSTFS_AUDIT_RETENTION_DAYS:=1}"

case "$RUSTFS_AUDIT_RETENTION_DAYS" in
  ''|*[!0-9]*) echo "RUSTFS_AUDIT_RETENTION_DAYS must be a positive integer" >&2; exit 2 ;;
esac

aws_s3() { aws --endpoint-url "$RUSTFS_ENDPOINT" "$@"; }

create_bucket() {
  bucket=$1
  if aws_s3 s3api head-bucket --bucket "$bucket" 2>/dev/null; then
    echo "bucket $bucket already exists"
  else
    # Object Lock requires versioning; this flag enables both at creation time.
    aws_s3 s3api create-bucket --bucket "$bucket" --object-lock-enabled-for-bucket >/dev/null
    echo "created $bucket (Object Lock enabled)"
  fi
}

create_bucket apex-attachments
create_bucket apex-csv
create_bucket apex-audit

# Default retention in COMPLIANCE mode: not even root can delete locked versions before expiry.
aws_s3 s3api put-object-lock-configuration \
  --bucket apex-audit \
  --object-lock-configuration "{\"ObjectLockEnabled\":\"Enabled\",\"Rule\":{\"DefaultRetention\":{\"Mode\":\"COMPLIANCE\",\"Days\":${RUSTFS_AUDIT_RETENTION_DAYS}}}}" >/dev/null

for bucket in apex-attachments apex-csv apex-audit; do
  aws_s3 s3api get-object-lock-configuration --bucket "$bucket" >/dev/null
done
echo "apex buckets ready (audit: COMPLIANCE ${RUSTFS_AUDIT_RETENTION_DAYS}d, dev only)"
