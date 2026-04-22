# comfy-aws

Run ComfyUI on AWS behind a clean REST API. FastAPI sidecar wraps ComfyUI's native HTTP server, exposing typed endpoints for model listing, workflow selection, KSampler parameter control, and async job execution. Infrastructure is defined in CDK (TypeScript) and targets ECS on EC2 GPU instances. Includes a React generation UI, API key auth, and CloudFront output delivery.

## Architecture

```
Internet → EC2 public IP :8000 → FastAPI sidecar ──── React UI (:8000/ui)
                                      │  (localhost)
                                  ComfyUI :8188  ←──── EBS /data/models
                                                             ↑
                                                      S3 sync on startup

Generated images: S3 (private) ←── CloudFront (signed URLs) ──→ Client
```

- **Compute**: ECS on EC2 `g4dn.xlarge` Spot (T4 GPU, 16GB VRAM), ASG min=0
- **API**: FastAPI sidecar in same ECS task as ComfyUI (no ALB — ~$0 idle cost)
- **Storage**: S3 for models + outputs; DynamoDB for job state; CloudFront for output delivery
- **Auth**: `X-API-Key` header middleware; comma-separated keys in `API_KEYS` env var
- **UI**: React + Vite + TypeScript at `/ui`; served as static files from the API container
- **Local dev**: `docker-compose` with ComfyUI (CPU mode) + LocalStack (S3/DynamoDB)

## API Endpoints

| Method   | Path              | Description                                                 |
| -------- | ----------------- | ----------------------------------------------------------- |
| `GET`    | `/health`         | ComfyUI reachability check (auth-exempt)                    |
| `GET`    | `/models`         | List checkpoints, LoRAs, VAEs                               |
| `GET`    | `/workflows`      | List available workflow templates                           |
| `GET`    | `/workflows/{id}` | Workflow parameter schema                                   |
| `POST`   | `/jobs`           | Submit a job `{workflow_id, params}`                        |
| `GET`    | `/jobs/{id}`      | Job status + signed image URLs (CloudFront or S3 presigned) |
| `DELETE` | `/jobs/{id}`      | Cancel a queued job                                         |
| `GET`    | `/ui`             | React generation UI (served from `frontend/dist/`)          |

All endpoints except `GET /health` require `X-API-Key` header when `API_KEYS` is set.

### Example

```bash
# Local dev (auth disabled by default)
BASE=http://localhost:8000

# AWS (replace with instance public IP; set API key if API_KEYS is configured)
BASE=http://<instance-public-ip>:8000
KEY=your-api-key

# List available models
curl $BASE/models
curl -H "X-API-Key: $KEY" $BASE/models   # when auth enabled

# Submit a txt2img job
curl -X POST $BASE/jobs \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $KEY" \
  -d '{
    "workflow_id": "txt2img-sdxl",
    "params": {
      "positive_prompt": "a red cat on a rooftop at sunset",
      "checkpoint": "sd_xl_base_1.0.safetensors",
      "steps": 25,
      "seed": 42
    }
  }'

# Poll for result (output_urls are CloudFront signed or S3 presigned)
curl $BASE/jobs/{job_id}

# Open the React UI
open http://localhost:8000/ui
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
    "positive_prompt": {
      "node_id": "6",
      "input": "text",
      "type": "string",
      "required": true
    },
    "steps": {
      "node_id": "3",
      "input": "steps",
      "type": "integer",
      "default": 20
    },
    "seed": {
      "node_id": "3",
      "input": "seed",
      "type": "integer",
      "default": -1
    }
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

# Open React UI (build first, or use Vite dev server below)
open http://localhost:8000/ui

# React dev server with hot reload (proxies /api → :8000)
cd frontend && npm install && npm run dev
# → http://localhost:5173

# Build React assets into frontend/dist/ (served by FastAPI at /ui)
cd frontend && npm run build

# Run unit tests (no external deps required)
cd api && pytest tests/test_workflow.py tests/test_auth_middleware.py tests/test_cdn.py -v

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
│   │   ├── comfy_client.py     # HTTP client for ComfyUI (submit + history poll)
│   │   ├── middleware/
│   │   │   └── auth.py         # ApiKeyMiddleware (X-API-Key header)
│   │   ├── routers/            # jobs, models, workflows, health
│   │   ├── services/
│   │   │   ├── job_service.py  # Job lifecycle (submit, watch, upload)
│   │   │   ├── dynamo.py       # DynamoDB read/write (stores output_keys)
│   │   │   ├── s3.py           # S3 upload; returns key (not URL)
│   │   │   ├── cdn.py          # CloudFront signed URL generation (RSA)
│   │   │   └── workflow.py     # Template load, merge_params, validate_params
│   │   └── models/             # pydantic models (job.py)
│   ├── workflows/              # workflow templates
│   │   └── txt2img-sdxl/
│   │       ├── workflow.json
│   │       └── schema.json
│   ├── tests/
│   └── Dockerfile
├── frontend/                   # React generation UI (Vite + TypeScript)
│   ├── src/
│   │   ├── App.tsx             # Root layout (sidebar + main + history)
│   │   ├── components/         # Sidebar, PromptForm, SettingsPanel, ResultPanel, etc.
│   │   └── hooks/              # useApi, useJob, useJobHistory
│   ├── vite.config.ts          # Proxy /api → :8000 for local dev
│   └── dist/                   # Built assets served by FastAPI at /ui (gitignored)
├── docker/
│   ├── comfyui/Dockerfile      # ComfyUI image (CPU + GPU modes)
│   └── model-sync/             # S3 → EBS sync init container
├── infra/                      # CDK TypeScript
│   └── lib/constructs/
│       ├── network.ts          # VPC, subnets, security groups
│       ├── storage.ts          # S3 bucket, DynamoDB table
│       ├── compute.ts          # ECS cluster, ASG g4dn.xlarge Spot
│       ├── service.ts          # ECS task def, IAM roles, SSM secrets
│       └── cdn.ts              # CloudFront distribution, OAC, key group
├── specs/                      # SDD specification documents
│   └── README.md               # Spec status tracker (v1–v5)
├── .claude/
│   ├── scripts/
│   │   ├── build-and-push.sh   # Cross-compile images for amd64, push to ECR
│   │   └── revoke-output.sh    # S3 delete + CloudFront invalidation for a job
│   └── commands/
│       └── revoke-output.md    # /revoke-output slash command
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

### Deploy with CloudFront (first time)

CloudFront requires an RSA-2048 key pair. Generate once and pass via CDK context:

```bash
# Generate key pair (keep cf_private.pem secret — it goes into SSM)
openssl genrsa -out cf_private.pem 2048
openssl rsa -pubout -in cf_private.pem -out cf_public.pem

# Deploy with CloudFront
npx cdk deploy --profile personal --require-approval never \
  -c cfPublicKey="$(cat cf_public.pem)" \
  -c cfPrivateKey="$(cat cf_private.pem)"
```

### Deploy on Apple Silicon (arm64 → amd64 cross-compile issues)

Docker Desktop's QEMU networking is unreliable for `linux/amd64` builds on M-series Macs.
Build and push images separately first, then deploy without Docker:

```bash
# Step 1 — build React UI first
cd frontend && npm run build && cd ..

# Step 2 — build and push images (uses docker buildx with docker-container driver)
bash .claude/scripts/build-and-push.sh personal

# Step 3 — deploy CloudFormation only (no Docker needed, uses pre-built images)
npx cdk deploy --profile personal --require-approval never \
  -c comfyuiImage=<uri printed by step 2> \
  -c apiImage=<uri printed by step 2>
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

See [`specs/README.md`](specs/README.md) for implementation status. v2–v5 complete; v1 has 2 remaining live-AWS tasks.

---

## Changelog

0.9.0

### Release Notes

#### v0.9.0 (2026-04-21)

- feat(auth): implement Bearer Token Auth (v9) [`873ccb8`]
- docs(.claude): add operator README for scripts and slash commands [`930ac6c`]
- style: apply code formatter across frontend, infra, and docs [`6a67fa1`]

#### v0.8.0 (2026-04-22)

- feat: add sync-to-aws.sh, model download API spec (v12), update aws profile [`a86f828`]

#### v0.7.1 (2026-04-21)

- test: add model-sync integration tests and AWS verification script [`a54eb1d`]

#### v0.7.0 (2026-04-21)

- feat: add img2img image upload pipeline [`627b8fc`]
- docs: add v8-v11 specs for img2img, auth, remote frontend, SSE previews [`c35f811`]

#### v0.6.0 (2026-04-01)

- feat: add image lightbox with full-screen overlay and copy-to-session [`2c5393d`]
- chore: add Vitest + React Testing Library test infrastructure [`f43819a`]
- docs: update README and CLAUDE.md to reflect v3-v5 implementation [`baec148`]

#### v0.5.0 (2026-03-27)

- feat: implement CloudFront output delivery (v3) [`5223406`]
- feat: implement React generation UI (v5) [`7916823`]
- feat: implement API key authentication middleware (v4) [`65a673e`]

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

| Layer     | Technology                                          |
| --------- | --------------------------------------------------- |
| API       | FastAPI, uvicorn, httpx, aioboto3, cryptography     |
| UI        | React, Vite, TypeScript, Tailwind CSS, Lucide React |
| Auth      | X-API-Key middleware; keys in SSM Parameter Store   |
| CDN       | CloudFront + OAC; RSA signed URLs generated locally |
| Infra     | AWS CDK v2 (TypeScript)                             |
| Compute   | ECS on EC2 g4dn.xlarge Spot                         |
| Storage   | S3, DynamoDB                                        |
| Local dev | Docker Compose, LocalStack                          |
| Tests     | pytest, pytest-asyncio (no mocks)                   |
