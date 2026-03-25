# CLAUDE.md — comfy-aws

## Project Overview

FastAPI wrapper around ComfyUI, deployed on AWS ECS (EC2 GPU). The API translates friendly typed requests into ComfyUI's raw node-graph workflow JSON and manages the full job lifecycle (submit → watch → S3 upload → status).

## Key Concepts

**Workflow templates**: Each template is a pair of files — `workflow.json` (raw ComfyUI graph with numeric node IDs) and `schema.json` (maps friendly param names to `{node_id, input}` pairs). The `merge_params()` function in `services/workflow.py` injects user params into the graph before submission.

**Job lifecycle**: `POST /jobs` → submit to ComfyUI `/prompt` → background asyncio task opens WebSocket to ComfyUI and watches execution events → on completion, download images from ComfyUI `/view` → upload to S3 → update DynamoDB with presigned URLs → status becomes COMPLETED.

**Sidecar pattern**: FastAPI and ComfyUI run in the same ECS task, sharing `localhost`. The sidecar calls `http://localhost:8188`. The ALB only routes to the sidecar (port 8000) — ComfyUI is never public-facing.

**LocalStack for local dev**: `AWS_ENDPOINT_URL=http://localstack:4566` redirects all boto3/aioboto3 calls to LocalStack. No code changes between local and AWS — no mocking.

## No Mocks Policy

**Never use mocks in tests.** Use real implementations:
- LocalStack for S3 and DynamoDB
- Real ComfyUI instance for HTTP/WebSocket tests
- If ComfyUI is unavailable: `pytest.skip("ComfyUI not available")` — not a mock

## File Purposes

| File | Purpose |
|------|---------|
| `api/app/comfy_client.py` | Async HTTP + WebSocket client for ComfyUI at `localhost:8188` |
| `api/app/services/job_service.py` | Full job lifecycle: create, submit, watch, upload, update |
| `api/app/services/workflow.py` | Template load/list, `merge_params()`, `validate_params()` |
| `api/app/services/dynamo.py` | aioboto3 DynamoDB read/write for job state |
| `api/app/services/s3.py` | aioboto3 S3 image upload + presigned URL generation |
| `api/app/config.py` | Pydantic Settings (env vars: COMFYUI_URL, S3_BUCKET, DYNAMO_TABLE) |
| `infra/lib/constructs/service.ts` | ECS task def: comfyui + api sidecar + model-sync init container |
| `infra/lib/constructs/compute.ts` | ECS cluster, ASG g4dn.xlarge Spot, EBS volumes, user data |
| `infra/lib/constructs/storage.ts` | S3 bucket (7-day lifecycle on outputs), DynamoDB (TTL, GSI) |
| `infra/lib/constructs/network.ts` | VPC, subnets, NAT, ALB/ECS security groups |
| `docker/comfyui/Dockerfile` | ComfyUI image; `--cpu` for local dev, GPU for AWS |
| `docker/model-sync/entrypoint.sh` | `aws s3 sync` init container; syncs models S3 → EBS |
| `docker-compose.yml` | Local dev: ComfyUI (CPU) + FastAPI + LocalStack |
| `docker-compose.gpu.yml` | GPU override for local GPU testing |

## Development Workflow

```bash
# Local dev
docker compose up -d
curl http://localhost:8000/health   # wait until 200

# Unit tests (no docker needed)
cd api && pytest tests/test_workflow.py -v

# Integration tests (requires docker-compose up)
cd api && pytest tests/ -v

# CDK
cd infra && npm install && cdk synth   # validate
cd infra && cdk deploy --all           # deploy to AWS
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMFYUI_URL` | `http://localhost:8188` | ComfyUI server address |
| `S3_BUCKET` | — | S3 bucket for models + outputs |
| `DYNAMO_TABLE` | — | DynamoDB table name for jobs |
| `AWS_DEFAULT_REGION` | — | AWS region |
| `AWS_ENDPOINT_URL` | — | Set to LocalStack URL in local dev |
| `PRESIGNED_URL_EXPIRY_SECONDS` | `3600` | Presigned URL lifetime |
| `JOB_TTL_DAYS` | `7` | DynamoDB job auto-expiry |

## AWS Infrastructure

- **ECS task**: 3 containers — `comfyui` (GPU, port 8188 internal), `api` (port 8000, ALB target), `model-sync` (init, exits after S3 sync)
- **ASG**: min=0, max=1, Spot with `ECS_ENABLE_SPOT_INSTANCE_DRAINING=true`
- **EBS**: 100GB root + 200GB data at `/data` (models at `/data/models`)
- **S3 key structure**: `models/checkpoints/`, `models/loras/`, `models/vae/`, `outputs/{job_id}/`
- **DynamoDB**: PK=`JOB#{id}`, TTL on `expires_at`, GSI on `status`+`created_at`

## Specs

Implementation tracked in `specs/README.md` — 25 tasks across 5 phases. Run `/sdd-next` to see the next task.
