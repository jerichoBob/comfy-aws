#!/usr/bin/env bash
# sync-to-aws.sh — Sync local models/workflows to S3, manage provider tokens, download models remotely.
#
# Usage:
#   bash .claude/scripts/sync-to-aws.sh [options]
#
# Sync options:
#   --models                  Sync ./models/ → s3://$S3_BUCKET/models/
#   --workflows               Sync ./api/workflows/ → s3://$S3_BUCKET/workflows/
#   --all                     Sync both (default when neither --models nor --workflows given)
#   --verify                  Scale up instance, wait for health, confirm GET /models
#   --scale-down              After --verify, scale the instance back to 0
#   --dry-run                 Show what would be synced without uploading
#
# Token management:
#   --set-token civitai <tok> Store CivitAI API token in SSM (/comfy-aws/civitai-token)
#   --set-token hf <tok>      Store HuggingFace token in SSM (/comfy-aws/hf-token)
#
# Remote download (requires API_HOST + COMFY_API_KEY in ~/.comfy-aws.env):
#   --download <url>          Trigger model download on the running instance
#   --type <type>             Model type: checkpoint | lora | vae (required with --download)
#   --filename <name>         Override inferred filename (optional)
#
# Requirements:
#   ~/.comfy-aws.env must contain: AWS_PROFILE, AWS_REGION, S3_BUCKET, ECS_CLUSTER, ECS_SERVICE
#   aws CLI must be authenticated (run: aws sts get-caller-identity --profile $AWS_PROFILE)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# ── Load env ──────────────────────────────────────────────────────────────────
ENV_FILE="$HOME/.comfy-aws.env"
[ -f "$ENV_FILE" ] && source "$ENV_FILE"

AWS_PROFILE="${AWS_PROFILE:-rwsjr-aws-new}"
AWS_REGION="${AWS_REGION:-us-east-1}"
S3_BUCKET="${S3_BUCKET:-}"
ECS_CLUSTER="${ECS_CLUSTER:-comfy-aws}"
ECS_SERVICE="${ECS_SERVICE:-}"

for var in S3_BUCKET ECS_CLUSTER ECS_SERVICE; do
    [ -z "${!var}" ] && { echo "✗ $var not set — add it to $ENV_FILE"; exit 1; }
done

# ── Parse args ────────────────────────────────────────────────────────────────
DO_MODELS=false
DO_WORKFLOWS=false
DO_VERIFY=false
DO_SCALE_DOWN=false
DRY_RUN=false
SET_TOKEN_PROVIDER=""
SET_TOKEN_VALUE=""
DOWNLOAD_URL=""
DOWNLOAD_TYPE=""
DOWNLOAD_FILENAME=""

args=("$@")
i=0
while [ $i -lt ${#args[@]} ]; do
    arg="${args[$i]}"
    case "$arg" in
        --models)     DO_MODELS=true ;;
        --workflows)  DO_WORKFLOWS=true ;;
        --all)        DO_MODELS=true; DO_WORKFLOWS=true ;;
        --verify)     DO_VERIFY=true ;;
        --scale-down) DO_SCALE_DOWN=true ;;
        --dry-run)    DRY_RUN=true ;;
        --set-token)
            i=$((i+1)); SET_TOKEN_PROVIDER="${args[$i]}"
            i=$((i+1)); SET_TOKEN_VALUE="${args[$i]}" ;;
        --download)
            i=$((i+1)); DOWNLOAD_URL="${args[$i]}" ;;
        --type)
            i=$((i+1)); DOWNLOAD_TYPE="${args[$i]}" ;;
        --filename)
            i=$((i+1)); DOWNLOAD_FILENAME="${args[$i]}" ;;
        --help|-h)
            sed -n '2,30p' "$0" | sed 's/^# //'
            exit 0 ;;
        *) echo "Unknown option: $arg"; exit 1 ;;
    esac
    i=$((i+1))
done

# ── Set provider token ────────────────────────────────────────────────────────
if [ -n "$SET_TOKEN_PROVIDER" ]; then
    case "$SET_TOKEN_PROVIDER" in
        civitai) SSM_PATH="/comfy-aws/civitai-token" ;;
        hf)      SSM_PATH="/comfy-aws/hf-token" ;;
        *) echo "✗ Unknown provider '$SET_TOKEN_PROVIDER' — use: civitai | hf"; exit 1 ;;
    esac
    [ -z "$SET_TOKEN_VALUE" ] && { echo "✗ Token value required"; exit 1; }
    $AWS ssm put-parameter \
        --name "$SSM_PATH" \
        --value "$SET_TOKEN_VALUE" \
        --type SecureString \
        --overwrite \
        --query 'Version' --output text > /dev/null
    echo "✓ Token stored at $SSM_PATH (version updated)"
    exit 0
fi

# ── Remote download via API ───────────────────────────────────────────────────
if [ -n "$DOWNLOAD_URL" ]; then
    COMFY_API_KEY="${COMFY_API_KEY:-}"
    API_HOST="${API_HOST:-}"
    [ -z "$API_HOST" ]      && { echo "✗ API_HOST not set in $ENV_FILE — run --verify first"; exit 1; }
    [ -z "$COMFY_API_KEY" ] && { echo "✗ COMFY_API_KEY not set in $ENV_FILE"; exit 1; }
    [ -z "$DOWNLOAD_TYPE" ] && { echo "✗ --type required (checkpoint | lora | vae)"; exit 1; }

    API_URL="http://$API_HOST:8000"
    BODY="{\"url\":\"$DOWNLOAD_URL\",\"type\":\"$DOWNLOAD_TYPE\""
    [ -n "$DOWNLOAD_FILENAME" ] && BODY="$BODY,\"filename\":\"$DOWNLOAD_FILENAME\""
    BODY="$BODY}"

    echo "→ Starting remote download on $API_HOST..."
    RESPONSE=$(curl -sf -X POST "$API_URL/admin/models/download" \
        -H "Authorization: Bearer $COMFY_API_KEY" \
        -H "Content-Type: application/json" \
        -d "$BODY")
    JOB_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])" 2>/dev/null)
    FILENAME=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['filename'])" 2>/dev/null)
    [ -z "$JOB_ID" ] && { echo "✗ Failed to start download: $RESPONSE"; exit 1; }
    echo "  Job $JOB_ID — downloading $FILENAME"

    echo "  Polling status..."
    STATUS=""
    while true; do
        STATUS=$(curl -sf "$API_URL/admin/models/downloads/$JOB_ID" \
            -H "Authorization: Bearer $COMFY_API_KEY" | \
            python3 -c "import sys,json; d=json.load(sys.stdin); print(d['status'])" 2>/dev/null)
        case "$STATUS" in
            ready)
                echo ""
                echo "  ✓ $FILENAME is ready"
                break ;;
            failed)
                ERROR=$(curl -sf "$API_URL/admin/models/downloads/$JOB_ID" \
                    -H "Authorization: Bearer $COMFY_API_KEY" | \
                    python3 -c "import sys,json; print(json.load(sys.stdin).get('error','unknown'))" 2>/dev/null)
                echo ""
                echo "  ✗ Download failed: $ERROR"
                exit 1 ;;
            *) printf "." ;;
        esac
        sleep 5
    done
    exit 0
fi

# ── Default: sync both if neither specified ───────────────────────────────────
if ! $DO_MODELS && ! $DO_WORKFLOWS; then
    DO_MODELS=true
    DO_WORKFLOWS=true
fi

AWS="aws --profile $AWS_PROFILE --region $AWS_REGION"
SYNC_FLAGS="--exact-timestamps --no-progress"
$DRY_RUN && SYNC_FLAGS="$SYNC_FLAGS --dryrun"

echo "comfy-aws sync"
echo "  Bucket:  s3://$S3_BUCKET"
echo "  Cluster: $ECS_CLUSTER"
$DRY_RUN && echo "  (dry run — no changes will be made)"
echo ""

# ── Sync models ───────────────────────────────────────────────────────────────
if $DO_MODELS; then
    MODELS_DIR="$REPO_ROOT/models"
    if [ ! -d "$MODELS_DIR" ]; then
        echo "⚠  No models/ directory found at $MODELS_DIR — skipping"
    else
        echo "→ Syncing models..."
        $AWS s3 sync "$MODELS_DIR/" "s3://$S3_BUCKET/models/" $SYNC_FLAGS
        # Count uploaded files
        COUNT=$(find "$MODELS_DIR" -type f ! -name ".gitkeep" | wc -l | tr -d ' ')
        echo "  ✓ $COUNT model file(s) synced to s3://$S3_BUCKET/models/"
    fi
    echo ""
fi

# ── Sync workflows ────────────────────────────────────────────────────────────
if $DO_WORKFLOWS; then
    WORKFLOWS_DIR="$REPO_ROOT/api/workflows"
    if [ ! -d "$WORKFLOWS_DIR" ]; then
        echo "⚠  No api/workflows/ directory found — skipping"
    else
        echo "→ Syncing workflows..."
        $AWS s3 sync "$WORKFLOWS_DIR/" "s3://$S3_BUCKET/workflows/" $SYNC_FLAGS
        COUNT=$(find "$WORKFLOWS_DIR" -name "*.json" | wc -l | tr -d ' ')
        echo "  ✓ $COUNT workflow file(s) synced to s3://$S3_BUCKET/workflows/"
    fi
    echo ""
fi

$DRY_RUN && { echo "Dry run complete."; exit 0; }

# ── Verify on live instance ───────────────────────────────────────────────────
if $DO_VERIFY; then
    echo "→ Scaling up ECS instance..."
    $AWS ecs update-service \
        --cluster "$ECS_CLUSTER" \
        --service "$ECS_SERVICE" \
        --desired-count 1 \
        --query 'service.desiredCount' --output text

    echo "  Waiting for EC2 instance to launch (this takes ~2 min)..."
    # Poll until a running instance with the cluster tag appears
    PUBLIC_IP=""
    for i in $(seq 1 40); do
        PUBLIC_IP=$($AWS ec2 describe-instances \
            --filters \
                "Name=tag:aws:cloudformation:stack-name,Values=ComfyAwsStack" \
                "Name=instance-state-name,Values=running" \
            --query 'Reservations[0].Instances[0].PublicIpAddress' \
            --output text 2>/dev/null || true)
        [ -n "$PUBLIC_IP" ] && [ "$PUBLIC_IP" != "None" ] && break
        printf "."
        sleep 10
    done
    echo ""
    [ -z "$PUBLIC_IP" ] || [ "$PUBLIC_IP" = "None" ] && { echo "✗ Instance did not launch in time"; exit 1; }
    echo "  Instance public IP: $PUBLIC_IP"

    API_URL="http://$PUBLIC_IP:8000"
    echo ""
    echo "→ Waiting for API health check at $API_URL/health..."
    for i in $(seq 1 60); do
        STATUS=$(curl -sf "$API_URL/health" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('status',''))" 2>/dev/null || true)
        [ "$STATUS" = "ok" ] && break
        printf "."
        sleep 10
    done
    echo ""
    [ "$STATUS" != "ok" ] && { echo "✗ API did not become healthy"; exit 1; }
    echo "  ✓ API healthy"

    echo ""
    echo "→ Verifying GET /models..."
    MODELS_JSON=$(curl -sf "$API_URL/models" 2>/dev/null)
    CHECKPOINTS=$(echo "$MODELS_JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
ckpts = data.get('checkpoints', [])
print('\n'.join(f'  • {c}' for c in ckpts) if ckpts else '  (none)')
" 2>/dev/null || echo "  (could not parse)")
    echo "  Checkpoints:"
    echo "$CHECKPOINTS"

    # Save API_HOST for future use
    if ! grep -q "^API_HOST=" "$ENV_FILE" 2>/dev/null; then
        echo "API_HOST=$PUBLIC_IP" >> "$ENV_FILE"
    else
        sed -i '' "s|^API_HOST=.*|API_HOST=$PUBLIC_IP|" "$ENV_FILE"
    fi
    echo ""
    echo "  API_HOST=$PUBLIC_IP saved to $ENV_FILE"

    if $DO_SCALE_DOWN; then
        echo ""
        echo "→ Scaling instance back to 0..."
        $AWS ecs update-service \
            --cluster "$ECS_CLUSTER" \
            --service "$ECS_SERVICE" \
            --desired-count 0 \
            --query 'service.desiredCount' --output text
        echo "  ✓ Scaled down"
    fi
fi

echo ""
echo "Done."
