#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="$(cd "$SCRIPT_DIR/../../infra" && pwd)"

echo "Deploying ComfyAwsStack from $INFRA_DIR..."
echo ""

cd "$INFRA_DIR"
JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION=1 npx cdk deploy \
  --profile personal \
  --require-approval never \
  2>&1
