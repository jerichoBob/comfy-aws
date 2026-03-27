#!/bin/sh
# model-sync init container
# Syncs models from S3 to the local /data/models directory.
# Runs once at ECS task startup and exits 0 on success.
set -e

: "${S3_BUCKET:?S3_BUCKET environment variable is required}"

echo "Syncing models from s3://${S3_BUCKET}/models/ to /data/models/ ..."

aws s3 sync \
  "s3://${S3_BUCKET}/models/" \
  "/data/models/" \
  --exact-timestamps \
  --no-progress

echo "Model sync complete."
