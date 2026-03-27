# comfy-aws

Run ComfyUI on AWS behind a clean REST API. FastAPI sidecar wraps ComfyUI's native HTTP server, exposing typed endpoints for model listing, workflow selection, KSampler parameter control, and async job execution. Infrastructure is defined in CDK (TypeScript) and targets ECS on EC2 GPU instances.

## Architecture

```
Internet → EC2 public IP :8000 → FastAPI sidecar
                                      │  (localhost)
                                  ComfyUI :8188  ←──── EBS /data/models
                                                             ↑
                                                      S3 sync on startup
```

- **Compute**: ECS on EC2 `g4dn.xlarge` Spot (T4 GPU, 16GB VRAM), ASG min=0
- **API**: FastAPI sidecar in same ECS task as ComfyUI (no ALB — ~$0 idle cost)
- **Storage**: S3 for models + generated outputs; DynamoDB for job state
- **Local dev**: `docker-compose` with ComfyUI (CPU mode) + LocalStack (S3/DynamoDB)

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | ComfyUI reachability check |
| `GET` | `/models` | List checkpoints, LoRAs, VAEs |
| `GET` | `/workflows` | List available workflow templates |
| `GET` | `/workflows/{id}` | Workflow parameter schema |
| `POST` | `/jobs` | Submit a job `{workflow_id, params}` |
| `GET` | `/jobs/{id}` | Job status + presigned S3 image URLs |
| `DELETE` | `/jobs/{id}` | Cancel a queued job |

### Example

```bash
# Local dev
BASE=http://localhost:8000

# AWS (replace with instance public IP)
BASE=http://<instance-public-ip>:8000

# List available models
curl $BASE/models

# Submit a txt2img job
curl -X POST $BASE/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "workflow_id": "txt2img-sdxl",
    "params": {
      "positive_prompt": "a red cat on a rooftop at sunset",
      "checkpoint": "sd_xl_base_1.0.safetensors",
      "steps": 25,
      "seed": 42
    }
  }'

# Poll for result
curl $BASE/jobs/{job_id}
```

## Workflow Template System

Each workflow is two files:

```
api/workflows/txt2img-sdxl/
├── workflow.json   # raw ComfyUI node graph
└── schema.json     # maps friendly param names → {node_id, input}
```

`schema.json` example:
```json
{
  "id": "txt2img-sdxl",
  "parameters": {
    "positive_prompt": {"node_id": "6", "input": "text", "type": "string", "required": true},
    "steps":           {"node_id": "3", "input": "steps", "type": "integer", "default": 20},
    "seed":            {"node_id": "3", "input": "seed",  "type": "integer", "default": -1}
  }
}
```

The API merges user params into the workflow graph before submitting to ComfyUI's `/prompt` endpoint.

## Local Development

```bash
# Start ComfyUI (CPU mode) + FastAPI + LocalStack
docker compose up

# Wait for ComfyUI to be ready (~60s on CPU)
curl http://localhost:8000/health

# Run unit tests (no external deps required)
cd api && pytest tests/test_workflow.py -v

# Run all integration tests (requires docker-compose running)
cd api && pytest tests/ -v
```

## Project Structure

```
comfy-aws/
├── api/                        # FastAPI sidecar (Python)
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── comfy_client.py     # HTTP + WebSocket bridge to ComfyUI
│   │   ├── routers/            # jobs, models, workflows
│   │   ├── services/           # job_service, dynamo, s3, workflow
│   │   └── models/             # pydantic models
│   ├── workflows/              # workflow templates (bundled in image)
│   │   └── txt2img-sdxl/
│   │       ├── workflow.json
│   │       └── schema.json
│   ├── tests/
│   └── Dockerfile
├── docker/
│   ├── comfyui/Dockerfile      # ComfyUI image (CPU + GPU modes)
│   └── model-sync/             # S3 → EBS sync init container
├── infra/                      # CDK TypeScript
│   └── lib/constructs/
│       ├── network.ts          # VPC, subnets, security groups
│       ├── storage.ts          # S3 bucket, DynamoDB table
│       ├── compute.ts          # ECS cluster, ASG g4dn.xlarge Spot
│       └── service.ts          # ECS task def, IAM roles (no ALB)
├── specs/                      # SDD specification documents
│   ├── README.md
│   └── spec-v1-comfy-aws.md
├── docker-compose.yml          # Local dev (CPU mode + LocalStack)
└── docker-compose.gpu.yml      # Local dev GPU override
```

## AWS Deployment

### One-time bootstrap

```bash
cd infra
npm install
npx cdk bootstrap --profile personal    # or --profile work
```

### Deploy (standard — requires Docker + internet)

```bash
npx cdk deploy --profile personal --require-approval never
```

### Deploy on Apple Silicon (arm64 → amd64 cross-compile issues)

Docker Desktop's QEMU networking is unreliable for `linux/amd64` builds on M-series Macs.
Build and push images separately first, then deploy without Docker:

```bash
# Step 1 — build images (uses docker buildx with docker-container driver)
bash .claude/scripts/build-and-push.sh personal

# Step 2 — deploy CloudFormation only (no Docker needed, uses pre-built images)
npx cdk deploy --profile personal --require-approval never \
  -c comfyuiImage=<uri printed by step 1> \
  -c apiImage=<uri printed by step 1>
```

### Spin up / spin down

```bash
# Find your ASG name
ASG=$(aws autoscaling describe-auto-scaling-groups --profile personal \
  --query 'AutoScalingGroups[?contains(AutoScalingGroupName,`ComfyAws`)].AutoScalingGroupName' \
  --output text)

# Spin up (starts g4dn.xlarge Spot, ~$0.16/hr)
aws autoscaling set-desired-capacity --auto-scaling-group-name $ASG \
  --desired-capacity 1 --profile personal

# Find the public IP once running (~60s)
aws ec2 describe-instances --profile personal \
  --filters Name=instance-state-name,Values=running \
  --query 'Reservations[].Instances[].PublicIpAddress' --output text

# Spin down (terminates instance, stops billing)
aws autoscaling set-desired-capacity --auto-scaling-group-name $ASG \
  --desired-capacity 0 --profile personal
```

### Upload models

```bash
# Sync a checkpoint to S3 (model-sync init container picks it up on next spin-up)
aws s3 cp sd_xl_base_1.0.safetensors \
  s3://{bucket}/models/checkpoints/sd_xl_base_1.0.safetensors --profile personal
```

## Specs

See [`specs/README.md`](specs/README.md) for the full implementation spec (v1, 25 tasks across 5 phases).

---

## Changelog

0.4.0

### Release Notes

#### v0.4.0 (2026-03-27)

- feat: add duration_seconds to job model and lifecycle tracking [`d22dc33`]
- docs: add v4 API key auth and v5 React UI specs [`0967e58`]

#### v0.3.0 (2026-03-27)

- fix: Convert float params to Decimal for DynamoDB compatibility [`169b727`]
- feat: Add sampler_name and scheduler params to txt2img-sdxl schema [`2cb68aa`]

#### v0.2.0 (2026-03-27)

- docs: Add v3 CloudFront output delivery spec and architecture diagrams [`12572ef`]

#### v0.1.0 (2026-03-27)

- feat: Add FastAPI sidecar with full job lifecycle [`8e22592`]
- feat: Add ComfyUI image, model-sync sidecar, and docker-compose stack [`0070d34`]
- feat: Add CDK stack for ECS-on-EC2 GPU deployment [`add4033`]
- chore: Scaffold models directory with gitkeep placeholders [`ff1082b`]
- chore: Update docs, specs, gitignore, and add Claude automation scripts [`73115b9`]

## Tech Stack

| Layer | Technology |
|-------|------------|
| API | FastAPI, uvicorn, httpx, aioboto3 |
| Infra | AWS CDK v2 (TypeScript) |
| Compute | ECS on EC2 g4dn.xlarge Spot |
| Storage | S3, DynamoDB |
| Local dev | Docker Compose, LocalStack |
| Tests | pytest, pytest-asyncio (no mocks) |
