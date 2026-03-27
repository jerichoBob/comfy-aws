# CLAUDE.md — comfy-aws

## Project Overview

FastAPI wrapper around ComfyUI, deployed on AWS ECS (EC2 GPU). The API translates friendly typed requests into ComfyUI's raw node-graph workflow JSON and manages the full job lifecycle (submit → watch → S3 upload → status).

## Key Concepts

**Workflow templates**: Each template is a pair of files — `workflow.json` (raw ComfyUI graph with numeric node IDs) and `schema.json` (maps friendly param names to `{node_id, input}` pairs). The `merge_params()` function in `services/workflow.py` injects user params into the graph before submission.

**Job lifecycle**: `POST /jobs` → submit to ComfyUI `/prompt` → background asyncio task polls `/history/{prompt_id}` every 2s → on completion, download images from ComfyUI `/view` → upload to S3 (stores S3 key in DynamoDB, not URL) → status becomes COMPLETED. URL generation happens at `GET /jobs/{id}` request time: CloudFront signed URL if `CLOUDFRONT_DOMAIN` is set, S3 presigned URL otherwise (local dev).

**Sidecar pattern**: FastAPI and ComfyUI run in the same ECS task, sharing `localhost`. The sidecar calls `http://localhost:8188`. The API is directly exposed on port 8000 (no ALB) — ComfyUI is never public-facing.

**API key auth**: `ApiKeyMiddleware` in `app/middleware/auth.py` checks `X-API-Key` header against `settings.api_key_set` (parsed from `API_KEYS` env var). Auth is disabled when `API_KEYS=""`. `GET /health` is always exempt.

**CloudFront output delivery**: `services/cdn.py` loads an RSA private key PEM from SSM at startup. `generate_signed_url()` creates CloudFront canned-policy signed URLs locally — zero per-request AWS calls. When `CLOUDFRONT_DOMAIN` is empty, `routers/jobs.py` falls back to S3 presigned URLs via `services/s3.py`.

**LocalStack for local dev**: `AWS_ENDPOINT_URL=http://localstack:4566` redirects all boto3/aioboto3 calls to LocalStack. No code changes between local and AWS — no mocking.

## No Mocks Policy

**Never use mocks in tests.** Use real implementations:
- LocalStack for S3 and DynamoDB
- Real ComfyUI instance for HTTP/WebSocket tests
- If ComfyUI is unavailable: `pytest.skip("ComfyUI not available")` — not a mock

## File Purposes

| File | Purpose |
|------|---------|
| `api/app/comfy_client.py` | Async HTTP client for ComfyUI: `submit_prompt()`, `get_history()`, `get_image()` |
| `api/app/middleware/auth.py` | `ApiKeyMiddleware`: checks `X-API-Key`; skips when `API_KEYS=""`; `/health` exempt |
| `api/app/services/job_service.py` | Job lifecycle: create, submit, poll history, upload, update DynamoDB |
| `api/app/services/workflow.py` | Template load/list, `merge_params()`, `validate_params()` |
| `api/app/services/dynamo.py` | DynamoDB read/write; stores `output_keys` (S3 keys, not URLs) |
| `api/app/services/s3.py` | S3 upload (returns key); `generate_presigned_url()` for local dev fallback |
| `api/app/services/cdn.py` | CloudFront signed URL generation; loads RSA key from SSM on startup |
| `api/app/routers/jobs.py` | Job endpoints; `_resolve_output_urls()` generates URLs at request time |
| `api/app/config.py` | Pydantic Settings (all env vars including API_KEYS, CLOUDFRONT_*) |
| `frontend/src/App.tsx` | Root layout: left sidebar + main prompt area + right history panel |
| `frontend/src/hooks/useJob.ts` | Job state machine: idle→submitting→polling→done\|failed (2s poll) |
| `frontend/src/hooks/useApi.ts` | Models + workflows fetch; `apiFetch()` wrapper injects `X-API-Key` |
| `infra/lib/constructs/cdn.ts` | CloudFront distribution, OAC, key group, S3 bucket deny policy |
| `infra/lib/constructs/service.ts` | ECS task def: comfyui + api sidecar + model-sync; pulls API_KEYS from SSM |
| `infra/lib/constructs/compute.ts` | ECS cluster, ASG g4dn.xlarge Spot, EBS volumes, user data |
| `infra/lib/constructs/storage.ts` | S3 bucket (7-day lifecycle on outputs), DynamoDB (TTL, GSI) |
| `infra/lib/constructs/network.ts` | VPC, subnets, security groups |
| `docker/comfyui/Dockerfile` | ComfyUI image; `--cpu` for local dev, GPU for AWS |
| `docker/model-sync/entrypoint.sh` | `aws s3 sync` init container; syncs models S3 → EBS |
| `docker-compose.yml` | Local dev: ComfyUI (CPU) + FastAPI + LocalStack |
| `docker-compose.gpu.yml` | GPU override for local GPU testing |
| `.claude/scripts/revoke-output.sh` | Delete S3 outputs + CloudFront invalidation for a job ID |

## Development Workflow

```bash
# Local dev (API + ComfyUI + LocalStack)
docker compose up -d
curl http://localhost:8000/health   # wait until 200

# React UI — dev server with hot reload (proxies /api → :8000)
cd frontend && npm install && npm run dev   # → http://localhost:5173

# Build UI for FastAPI serving at /ui
cd frontend && npm run build

# Unit tests (no docker needed)
cd api && pytest tests/test_workflow.py tests/test_auth_middleware.py tests/test_cdn.py -v

# Integration tests (requires docker-compose up)
cd api && pytest tests/ -v

# CDK
cd infra && npm install && cdk synth   # validate
cd infra && cdk deploy --all           # deploy to AWS (without CloudFront)
cd infra && cdk deploy --all \
  -c cfPublicKey="$(cat cf_public.pem)" \
  -c cfPrivateKey="$(cat cf_private.pem)"  # with CloudFront
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
| `API_KEYS` | `""` | Comma-separated valid API keys; empty disables auth. In AWS, sourced from SSM `/comfy-aws/api-keys` |
| `CLOUDFRONT_DOMAIN` | `""` | CloudFront domain for signed URLs; empty = local dev (falls back to S3 presigned) |
| `CLOUDFRONT_KEY_PAIR_ID` | `""` | CloudFront key pair ID for signed URL signing |
| `CLOUDFRONT_PRIVATE_KEY_SSM_PATH` | `/comfy-aws/cloudfront-private-key` | SSM path for RSA private key PEM |

## AWS Infrastructure

- **ECS task**: 3 containers — `comfyui` (GPU, port 8188 internal), `api` (port 8000, ALB target), `model-sync` (init, exits after S3 sync)
- **ASG**: min=0, max=1, Spot with `ECS_ENABLE_SPOT_INSTANCE_DRAINING=true`
- **EBS**: 100GB root + 200GB data at `/data` (models at `/data/models`)
- **S3 key structure**: `models/checkpoints/`, `models/loras/`, `models/vae/`, `outputs/{job_id}/`
- **DynamoDB**: PK=`JOB#{id}`, TTL on `expires_at`, GSI on `status`+`created_at`

## Specs

Implementation tracked in `specs/README.md`. v2 (e2e test), v3 (CloudFront), v4 (API auth), v5 (React UI) all complete. v1 has 2 remaining live-AWS tasks (model-sync integration test). Run `/sdd-next` to see the next task.
