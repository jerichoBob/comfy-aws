# .claude — Operator Toolkit

Scripts and Claude slash commands for managing the comfy-aws deployment.

All scripts read credentials and stack config from `~/.comfy-aws.env`:

```bash
AWS_PROFILE=rwsjr-aws-new
AWS_REGION=us-east-1
S3_BUCKET=comfyawsstack-storagebucket5cb7c8ea-utcimxpqfqlj
DYNAMO_TABLE=ComfyAwsStack-StorageJobsTable47C44CDA-136GD00SOS9IR
ECS_CLUSTER=comfy-aws
ECS_SERVICE=ComfyAwsStack-Service9571FDD8-bwuJmT3uWCo9
API_HOST=<public IP — set automatically by sync-to-aws.sh --verify>
COMFY_API_KEY=<your API key — matches SSM /comfy-aws/api-keys>
```

---

## Scripts

### `sync-to-aws.sh` — Day-to-day operator tool

Syncs local models/workflows to S3, manages provider tokens, scales the instance, and triggers remote model downloads.

```bash
# Sync everything (models + workflows) to S3
bash .claude/scripts/sync-to-aws.sh

# Sync models only
bash .claude/scripts/sync-to-aws.sh --models

# Sync workflows only (hot-reload without instance restart)
bash .claude/scripts/sync-to-aws.sh --workflows

# Scale up, wait for health, verify GET /models, save API_HOST to env
bash .claude/scripts/sync-to-aws.sh --verify

# Full deploy: sync → scale up → verify → scale back down
bash .claude/scripts/sync-to-aws.sh --verify --scale-down

# Preview without uploading
bash .claude/scripts/sync-to-aws.sh --dry-run

# Store a model provider token in SSM (one-time setup)
bash .claude/scripts/sync-to-aws.sh --set-token civitai <token>
bash .claude/scripts/sync-to-aws.sh --set-token hf <token>

# Trigger a remote model download on the running instance
bash .claude/scripts/sync-to-aws.sh --download https://civitai.com/api/download/models/12345 --type checkpoint
bash .claude/scripts/sync-to-aws.sh --download https://huggingface.co/... --type lora --filename my-lora.safetensors
```

Model provider tokens are stored in SSM as SecureString and applied automatically by the API based on URL domain — you don't pass them per-request.

---

### `build-and-push.sh` — Build Docker images for AWS

Builds the ComfyUI and API images for `linux/amd64` using `docker buildx` and pushes to ECR. Required before CDK deploy on Apple Silicon (QEMU networking issues prevent inline CDK builds).

```bash
bash .claude/scripts/build-and-push.sh rwsjr-aws-new
```

Prints the `cdk deploy -c comfyuiImage=... -c apiImage=...` command to run after.

---

### `cfn-deploy.sh` — Deploy the stack

Thin wrapper around `cdk deploy`. Use `/cfn-deploy` (the slash command) instead — it streams output and runs `/cfn-status` on completion.

```bash
bash .claude/scripts/cfn-deploy.sh
```

---

### `revoke-output.sh` — Delete job outputs

Deletes all S3 objects for a job ID and creates a CloudFront invalidation. Use `/revoke-output` (the slash command) instead for the guided flow.

```bash
S3_BUCKET=<bucket> CLOUDFRONT_DISTRIBUTION_ID=<id> \
  bash .claude/scripts/revoke-output.sh <job-id>
```

---

### `test-model-sync-aws.sh` — Verify model sync on live AWS

Uploads a checkpoint to S3, forces an ECS task restart, waits for the API to become healthy, and asserts the model appears in `GET /models`. Run this after first deployment or when validating a new checkpoint.

```bash
bash .claude/scripts/test-model-sync-aws.sh ./models/checkpoints/your-model.safetensors
```

Requires `S3_BUCKET`, `ECS_CLUSTER`, `ECS_SERVICE`, and `API_HOST` in `~/.comfy-aws.env`.

---

## Slash Commands

Run these inside Claude Code (prefix with `/`).

| Command | What it does |
|---------|-------------|
| `/cfn-deploy` | Run CDK deploy, stream output, show final stack status |
| `/cfn-status` | Show stack status + last 10 events with interpreted advice |
| `/cfn-watch` | Poll stack every 15s until stable — use while a deploy is running |
| `/cfn-events [N]` | Show last N CloudFormation events (default 30) |
| `/revoke-output` | Delete S3 outputs + CloudFront invalidation for a job ID |

---

## Common Workflows

### First deployment

```bash
# 1. Build and push Docker images
bash .claude/scripts/build-and-push.sh rwsjr-aws-new

# 2. Deploy the stack (use the cdk command printed by step 1)
# or just:
/cfn-deploy

# 3. Store provider tokens (optional, one-time)
bash .claude/scripts/sync-to-aws.sh --set-token civitai <token>
bash .claude/scripts/sync-to-aws.sh --set-token hf <token>

# 4. Upload models and verify
bash .claude/scripts/sync-to-aws.sh --verify
```

### Adding a new model

```bash
# Option A: copy locally then sync
cp ~/Downloads/my-model.safetensors models/checkpoints/
bash .claude/scripts/sync-to-aws.sh --models

# Option B: download directly on the instance (faster, no local copy)
bash .claude/scripts/sync-to-aws.sh --download <civitai-or-hf-url> --type checkpoint
```

### Adding a new workflow

```bash
# Create api/workflows/my-workflow/{workflow.json,schema.json}
bash .claude/scripts/sync-to-aws.sh --workflows
# Workflow is available immediately — no instance restart needed (v8 dynamic loading)
```

### Updating the API or ComfyUI image

```bash
bash .claude/scripts/build-and-push.sh rwsjr-aws-new
/cfn-deploy
```
