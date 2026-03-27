#!/bin/bash
# Build and push comfy-aws Docker images to ECR independently of CDK deploy.
#
# Why: CDK's inline Docker builds run under QEMU (arm64→amd64) with broken
# networking on Apple Silicon. This script uses docker buildx with the
# docker-container driver which has reliable networking.
#
# Usage:
#   bash .claude/scripts/build-and-push.sh personal
#   bash .claude/scripts/build-and-push.sh work
#
# After running, copy the printed cdk deploy command to deploy without Docker.
set -euo pipefail

PROFILE="${1:-personal}"
REGION="us-east-1"
ACCOUNT=$(aws sts get-caller-identity --profile "$PROFILE" --query Account --output text)
ECR_REGISTRY="${ACCOUNT}.dkr.ecr.${REGION}.amazonaws.com"
COMFYUI_REPO="comfy-aws/comfyui"
API_REPO="comfy-aws/api"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "==> Account:  $ACCOUNT"
echo "==> Registry: $ECR_REGISTRY"
echo ""

# Ensure ECR repos exist
for repo in "$COMFYUI_REPO" "$API_REPO"; do
  aws ecr describe-repositories --repository-names "$repo" \
    --profile "$PROFILE" --region "$REGION" &>/dev/null || \
  aws ecr create-repository --repository-name "$repo" \
    --profile "$PROFILE" --region "$REGION" --output text --query 'repository.repositoryUri'
done

# Login to ECR
echo "==> Logging in to ECR..."
aws ecr get-login-password --region "$REGION" --profile "$PROFILE" | \
  docker login --username AWS --password-stdin "$ECR_REGISTRY"

# Create a proper buildx builder with docker-container driver (reliable networking)
BUILDER="comfy-aws-builder"
if ! docker buildx inspect "$BUILDER" &>/dev/null; then
  echo "==> Creating buildx builder '$BUILDER'..."
  docker buildx create --name "$BUILDER" --driver docker-container --use
else
  docker buildx use "$BUILDER"
fi

COMFYUI_URI="${ECR_REGISTRY}/${COMFYUI_REPO}:latest"
API_URI="${ECR_REGISTRY}/${API_REPO}:latest"

# Build + push ComfyUI image
echo ""
echo "==> Building ComfyUI image (slow — installs CPU torch)..."
docker buildx build \
  --builder "$BUILDER" \
  --platform linux/amd64 \
  --tag "$COMFYUI_URI" \
  --push \
  "${REPO_ROOT}/docker/comfyui"

# Build + push API image
echo ""
echo "==> Building API image..."
docker buildx build \
  --builder "$BUILDER" \
  --platform linux/amd64 \
  --tag "$API_URI" \
  --push \
  "${REPO_ROOT}/api"

echo ""
echo "======================================================"
echo "Images pushed successfully:"
echo "  ComfyUI: $COMFYUI_URI"
echo "  API:     $API_URI"
echo ""
echo "Now deploy (no Docker needed):"
echo ""
echo "  cd \"${REPO_ROOT}/infra\" && \\"
echo "  JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 npx cdk deploy \\"
echo "    --profile $PROFILE \\"
echo "    --require-approval never \\"
echo "    -c comfyuiImage=$COMFYUI_URI \\"
echo "    -c apiImage=$API_URI"
echo "======================================================"
