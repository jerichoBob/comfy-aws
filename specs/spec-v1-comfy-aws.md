---
version: 1
name: comfy-aws
display_name: "ComfyUI on AWS"
status: draft
created: 2026-03-24
depends_on: []
tags: [aws, comfyui, fastapi, ecs, cdk, image-generation]
---

# ComfyUI on AWS

## Why (Problem Statement)

> As a developer, I want to run ComfyUI on AWS behind a clean REST API so that I can programmatically generate images with fine-grained control over models, workflows, and sampler parameters.

### Context

- ComfyUI is a powerful node-based AI image generation UI with a built-in HTTP server (port 8188)
- Running it locally requires a GPU workstation; running it in the cloud enables headless, API-driven usage from any client
- The native ComfyUI API is low-level (raw workflow JSON with numeric node IDs) — a wrapper API is needed to expose friendly, typed endpoints
- Workflows built in the ComfyUI UI can be exported as JSON and handed to the API for installation and invocation without needing the UI in production
- Stretch goal: optionally expose the ComfyUI UI itself via the ALB for workflow development

---

## What (Requirements)

### User Stories

- **US-1**: As an API consumer, I want to list available checkpoints, LoRAs, and VAEs so I can see what models are installed
- **US-2**: As an API consumer, I want to list available workflow templates and retrieve their parameter schemas so I know what inputs each workflow accepts
- **US-3**: As an API consumer, I want to submit a job with a workflow ID and typed parameters (prompts, steps, CFG, seed, dimensions) so I can generate images without constructing raw ComfyUI JSON
- **US-4**: As an API consumer, I want to poll a job by ID and receive presigned S3 URLs for completed images
- **US-5**: As an API consumer, I want to cancel a queued or running job
- **US-6**: As a developer, I want to build and test workflows locally using docker-compose (CPU mode, no GPU required) before deploying to AWS
- **US-7**: As a developer, I want to upload models to S3 and have them automatically synced to the ECS instance on startup

### Acceptance Criteria

- AC-1: `GET /models` returns a grouped list of checkpoints, loras, and vaes from the live ComfyUI instance
- AC-2: `POST /jobs` with `{workflow_id, params}` returns a job ID within 500ms; params are validated against the workflow schema before submission
- AC-3: `GET /jobs/{id}` transitions through PENDING → RUNNING → COMPLETED and returns presigned S3 image URLs on completion
- AC-4: `DELETE /jobs/{id}` cancels a queued job; returns 409 if already running or completed
- AC-5: All endpoints respond within SLA even when ComfyUI is loading models (health check delays ALB routing until ComfyUI is ready)
- AC-6: `docker compose up` starts a working local dev environment; `POST /jobs` completes a CPU-mode generation end-to-end
- AC-7: A model uploaded to `s3://{bucket}/models/checkpoints/` appears in `GET /models` after an ECS task restart

### Out of Scope

- Authentication / authorization (Cognito, API keys) — Phase 2 of hardening
- Horizontal scaling beyond a single ECS task (multi-GPU sharding via SQS) — future spec
- Real-time streaming of generation progress to the client (WebSocket proxy) — future spec
- ComfyUI custom node installation via the API — manual Docker image rebuild for now

---

## How (Approach)

### Phase 1: API Foundation

- Initialize `api/` Python project with FastAPI, pydantic-settings, httpx, aioboto3, pytest-asyncio
- Implement `config.py` (pydantic Settings), `models/job.py`, `models/workflow.py`
- Implement `services/workflow.py`: load template files, list templates, merge user params into workflow JSON, validate required params and types
- Create first workflow template `api/workflows/txt2img-sdxl/` with `workflow.json` (SDXL ComfyUI graph) and `schema.json` (param → node mapping)
- Write and pass `tests/test_workflow.py` unit tests (pure Python, no network, no ComfyUI required)

### Phase 2: Local Dev Environment

- Create `docker/comfyui/Dockerfile` (CPU mode: `--cpu` flag, pytorch base image, ComfyUI from GitHub)
- Create `docker-compose.yml` with three services: comfyui (port 8188), api (port 8000), localstack (port 4566 — S3 + DynamoDB)
- Implement `app/comfy_client.py`: async HTTP client for submit/history/models + WebSocket execution watcher
- Implement `services/dynamo.py` and `services/s3.py` using aioboto3 (pointed at LocalStack via `AWS_ENDPOINT_URL`)
- Implement `services/job_service.py`: create job → submit to ComfyUI → background asyncio WebSocket watch → upload images to S3 → update DynamoDB
- Implement all routers (`jobs.py`, `models.py`, `workflows.py`) and write integration tests against live docker-compose stack

### Phase 3: CDK Infrastructure

- Initialize `infra/` CDK TypeScript project (`cdk init app --language typescript`)
- Implement `NetworkConstruct`: VPC (2 AZs), public/private subnets, NAT Gateway, ALB/ECS security groups
- Implement `StorageConstruct`: S3 bucket (versioning, 7-day lifecycle for outputs, CORS), DynamoDB table (PAY_PER_REQUEST, TTL, GSI on status+created_at)
- Implement `ComputeConstruct`: ECS cluster, Launch Template (GPU AMI, 100GB root EBS + 200GB data EBS at `/data`), ASG (min=0 max=1), Spot capacity provider, user data (mount EBS, enable spot draining)
- Implement `ServiceConstruct`: ECS task definition (comfyui container with GPU resource + api sidecar + model-sync init container), ALB target group (health check `/health`), ECS service with Spot capacity provider strategy

### Phase 4: Model Management

- Define S3 key structure: `models/checkpoints/`, `models/loras/`, `models/vae/`
- Write model-sync init container script (`docker/model-sync/entrypoint.sh`): `aws s3 sync s3://{bucket}/models /data/models --exact-timestamps`
- Upload a real SDXL checkpoint to S3 and verify it appears in `GET /models` after ECS task restart
- Write integration test for full model-sync flow: upload → restart task → verify model listed

### Phase 5: Hardening

- Add structured JSON logging (python-json-logger) with `job_id` injected into every log record
- Add CloudWatch custom metrics: job queue depth, generation duration, error count
- Add job timeout handling: background task detects stale RUNNING jobs and transitions to FAILED
- Create second workflow template `api/workflows/img2img-sdxl/` to validate template system generality
- Add `docker-compose.gpu.yml` override (NVIDIA GPU passthrough, remove `--cpu` flag)

---

## Technical Notes

### Architecture Decisions

- **ECS on EC2 (not Fargate)**: Fargate does not support GPU instances; EC2 g4dn.xlarge (T4, 16GB VRAM) is the minimum viable GPU instance
- **FastAPI sidecar (not separate service)**: Both containers in the same ECS task share `localhost`; sidecar calls `http://localhost:8188` with no network latency or service discovery
- **ALB routes to sidecar only**: ComfyUI port 8188 is never exposed to the ALB; all external traffic goes through the API on port 8000
- **Spot Instances with SPOT_DRAINING**: `ECS_ENABLE_SPOT_INSTANCE_DRAINING=true` gives tasks 2-minute graceful shutdown; acceptable since generation jobs complete in 5-30 seconds
- **LocalStack for local dev**: Same boto3/aioboto3 code paths work locally and on AWS via `AWS_ENDPOINT_URL` environment variable — no mocking required
- **DynamoDB TTL for job cleanup**: Jobs auto-expire after 7 days; presigned S3 URLs expire after 1 hour (callers must download images before expiry)
- **Workflow schema as param → node mapping**: `schema.json` maps human-readable param names to `{node_id, input}` pairs; `merge_params()` injects values into the workflow graph before submission

### Dependencies

- ComfyUI (GitHub: comfyanonymous/ComfyUI)
- FastAPI + uvicorn + httpx + aioboto3 + pydantic-settings + websockets
- AWS CDK v2 (TypeScript)
- AWS services: ECS, EC2 (g4dn.xlarge), ALB, S3, DynamoDB, ECR, CloudWatch
- LocalStack (local dev only)
- Docker + NVIDIA Container Toolkit (GPU mode)

### Key File Paths

- `api/app/comfy_client.py` — HTTP + WebSocket bridge to ComfyUI
- `api/app/services/job_service.py` — full job lifecycle orchestration
- `api/app/services/workflow.py` — template loading and param merging (most testable logic)
- `infra/lib/constructs/service.ts` — ECS task definition, container deps, IAM, ALB wiring
- `docker-compose.yml` — local dev environment definition

### Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Spot instance interruption mid-job | 2-min drain window; jobs are short (5-30s); retry logic in client |
| API sidecar crash leaves job in RUNNING state | DynamoDB TTL on RUNNING state + recovery on next job_service startup |
| ComfyUI takes 60-120s to load models | ALB health check targets `/health` which only returns 200 when ComfyUI's `/system_stats` responds |
| Large model S3 sync on every task start | `--exact-timestamps` flag skips files already present on EBS |
| g4dn.xlarge insufficient VRAM for large models | Upgrade to g5.xlarge (A10G, 24GB) by changing single CDK parameter |

---

## Open Questions

1. Should the API support uploading workflow JSON directly (bypassing the template system) for power users?
2. What image output formats should be supported — PNG only, or also JPEG/WebP with quality settings?
3. Should job results be returned as inline base64 in `GET /jobs/{id}` as well as presigned URLs, for small clients that can't follow redirects?

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-24 | Initial draft |
