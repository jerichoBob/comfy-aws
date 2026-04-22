#!/usr/bin/env bash
# Verify model-sync on a live AWS deployment.
# Usage: bash .claude/scripts/test-model-sync-aws.sh <checkpoint-file> [--profile <profile>]
#
# What it does:
#   1. Uploads the given checkpoint file to S3 under models/checkpoints/
#   2. Forces an ECS task restart (new deployment triggers model-sync init container)
#   3. Waits for the API health check to pass
#   4. Calls GET /models and verifies the checkpoint appears
#
# Required env vars (or set via ~/.comfy-aws.env):
#   S3_BUCKET      — from CDK output ComfyAwsStack.BucketName
#   ECS_CLUSTER    — from CDK output ComfyAwsStack.ClusterName
#   ECS_SERVICE    — from CDK output ComfyAwsStack.ServiceName
#   API_HOST       — public IP or hostname of the running ECS instance (port 8000)

set -euo pipefail

# Load env file if present
[ -f ~/.comfy-aws.env ] && source ~/.comfy-aws.env

CHECKPOINT_FILE="${1:-}"
AWS_PROFILE="${3:-${AWS_PROFILE:-default}}"

if [ -z "$CHECKPOINT_FILE" ]; then
    echo "Usage: $0 <checkpoint-file> [--profile <aws-profile>]"
    echo "Example: $0 ./models/checkpoints/sd_xl_base_1.0.safetensors"
    exit 1
fi

if [ ! -f "$CHECKPOINT_FILE" ]; then
    echo "Error: file not found: $CHECKPOINT_FILE"
    exit 1
fi

for var in S3_BUCKET ECS_CLUSTER ECS_SERVICE API_HOST; do
    [ -z "${!var:-}" ] && { echo "Error: $var is not set. Add to ~/.comfy-aws.env or export it."; exit 1; }
done

FILENAME=$(basename "$CHECKPOINT_FILE")
S3_KEY="models/checkpoints/$FILENAME"

echo "=== Step 1: Upload checkpoint to S3 ==="
aws s3 cp "$CHECKPOINT_FILE" "s3://$S3_BUCKET/$S3_KEY" --profile "$AWS_PROFILE"
echo "  Uploaded: s3://$S3_BUCKET/$S3_KEY"

echo ""
echo "=== Step 2: Force ECS task restart ==="
aws ecs update-service \
    --cluster "$ECS_CLUSTER" \
    --service "$ECS_SERVICE" \
    --force-new-deployment \
    --profile "$AWS_PROFILE" \
    --query 'service.deployments[0].status' \
    --output text

echo "  Restart triggered. Waiting for new task to reach RUNNING..."

# Wait for service to stabilize (model-sync runs at startup, may take 2-5 min)
aws ecs wait services-stable \
    --cluster "$ECS_CLUSTER" \
    --services "$ECS_SERVICE" \
    --profile "$AWS_PROFILE"
echo "  Service stable."

echo ""
echo "=== Step 3: Wait for API health check ==="
API_URL="http://$API_HOST:8000"
ATTEMPTS=0
MAX_ATTEMPTS=30
until curl -sf "$API_URL/health" > /dev/null 2>&1; do
    ATTEMPTS=$((ATTEMPTS + 1))
    if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
        echo "  Error: API did not become healthy after $MAX_ATTEMPTS attempts."
        exit 1
    fi
    echo "  Waiting for API... ($ATTEMPTS/$MAX_ATTEMPTS)"
    sleep 10
done
echo "  API is healthy."

echo ""
echo "=== Step 4: Verify checkpoint in GET /models ==="
MODELS=$(curl -sf "$API_URL/models")
echo "  Response: $MODELS"

if echo "$MODELS" | grep -q "$FILENAME"; then
    echo ""
    echo "PASS: '$FILENAME' found in GET /models response."
    exit 0
else
    echo ""
    echo "FAIL: '$FILENAME' NOT found in GET /models response."
    echo "  Check that the model synced to /data/models/checkpoints/ on the ECS instance."
    echo "  Run: manage.sh exec comfyui 'ls /app/models/checkpoints/'"
    exit 1
fi
