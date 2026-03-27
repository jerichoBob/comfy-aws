#!/usr/bin/env bash
# revoke-output.sh <job_id> [--profile <aws_profile>]
#
# Revokes all output images for a job:
#   1. Deletes S3 objects at outputs/{job_id}/
#   2. Creates a CloudFront invalidation for /outputs/{job_id}/*
#
# Usage:
#   bash .claude/scripts/revoke-output.sh <job_id>
#   bash .claude/scripts/revoke-output.sh <job_id> --profile personal
#
# Prerequisites:
#   - AWS CLI configured with appropriate credentials
#   - S3_BUCKET environment variable set, or pass bucket name as second positional arg
#   - CLOUDFRONT_DISTRIBUTION_ID environment variable set, or derive from CDK stack outputs

set -euo pipefail

JOB_ID="${1:-}"
PROFILE_FLAG=""

# Parse optional --profile flag
shift 2>/dev/null || true
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE_FLAG="--profile $2"; shift 2 ;;
    *) shift ;;
  esac
done

if [[ -z "$JOB_ID" ]]; then
  echo "Usage: $0 <job_id> [--profile <aws_profile>]" >&2
  exit 1
fi

# Resolve S3 bucket
BUCKET="${S3_BUCKET:-}"
if [[ -z "$BUCKET" ]]; then
  echo "ERROR: S3_BUCKET environment variable not set" >&2
  exit 1
fi

# Resolve CloudFront distribution ID
DIST_ID="${CLOUDFRONT_DISTRIBUTION_ID:-}"
if [[ -z "$DIST_ID" ]]; then
  echo "ERROR: CLOUDFRONT_DISTRIBUTION_ID environment variable not set" >&2
  echo "  Find it with: aws cloudfront list-distributions --query 'DistributionList.Items[*].[Id,DomainName]' --output table $PROFILE_FLAG" >&2
  exit 1
fi

S3_PREFIX="outputs/${JOB_ID}/"

echo "Revoking job ${JOB_ID}..."
echo "  Bucket:       s3://${BUCKET}/${S3_PREFIX}"
echo "  Distribution: ${DIST_ID}"
echo ""

# Step 1: Delete S3 objects
echo "[1/2] Deleting S3 objects..."
# shellcheck disable=SC2086
aws s3 rm "s3://${BUCKET}/${S3_PREFIX}" --recursive $PROFILE_FLAG
echo "      Done."

# Step 2: CloudFront invalidation
echo "[2/2] Creating CloudFront invalidation..."
# shellcheck disable=SC2086
INVALIDATION=$(aws cloudfront create-invalidation \
  --distribution-id "${DIST_ID}" \
  --paths "/${S3_PREFIX}*" \
  --query 'Invalidation.Id' \
  --output text \
  $PROFILE_FLAG)
echo "      Invalidation ID: ${INVALIDATION}"
echo "      Status will be COMPLETED within ~60 seconds."
echo ""
echo "Revocation complete for job ${JOB_ID}."
