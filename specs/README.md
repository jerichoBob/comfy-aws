# comfy-aws Specs

## Quick Status

| Version | Name | Progress | Status | Owner |
|---------|------|----------|--------|-------|
| v1 | ComfyUI on AWS | 23/25 | 🔧 In Progress | robert.w.seaton.jr@gmail.com |
| v2 | Local E2E Generation Test | 4/4 | ✅ Complete | robert.w.seaton.jr@gmail.com |
| v3 | CloudFront Output Delivery | 0/11 | ✏️ Draft | — |
| v4 | API Key Authentication | 8/8 | ✅ Complete | — |
| v5 | React Generation UI | 15/15 | ✅ Complete | — |

---

## v1: ComfyUI on AWS

**Spec**: [spec-v1-comfy-aws.md](spec-v1-comfy-aws.md)

### Phase 1: API Foundation

- [x] Initialize `api/` Python project (FastAPI, pydantic-settings, httpx, aioboto3, pytest-asyncio)
- [x] Implement `config.py`, `models/job.py`, `models/workflow.py`
- [x] Implement `services/workflow.py` (load, list, merge, validate)
- [x] Create `api/workflows/txt2img-sdxl/` template (`workflow.json` + `schema.json`)
- [x] Write and pass `tests/test_workflow.py` unit tests (no external deps)

### Phase 2: Local Dev Environment

- [x] Create `docker/comfyui/Dockerfile` (CPU mode)
- [x] Create `docker-compose.yml` (ComfyUI + FastAPI + LocalStack)
- [x] Implement `app/comfy_client.py` (HTTP submit + WebSocket watch)
- [x] Implement `services/dynamo.py` and `services/s3.py` with aioboto3
- [x] Implement `services/job_service.py` (full async job lifecycle)
- [x] Write and pass integration tests against live docker-compose stack

### Phase 3: CDK Infrastructure

- [x] Initialize `infra/` CDK TypeScript project
- [x] Implement `NetworkConstruct` (VPC, subnets, NAT, security groups)
- [x] Implement `StorageConstruct` (S3 bucket, DynamoDB table)
- [x] Implement `ComputeConstruct` (ECS cluster, ASG g4dn.xlarge Spot, EBS volumes)
- [x] Implement `ServiceConstruct` (ECS task def with sidecar + init container, ALB)

### Phase 4: Model Management

- [x] Define S3 key structure for model types
- [x] Write model-sync init container script (`docker/model-sync/entrypoint.sh`)
- [ ] Upload test checkpoint to S3, verify in `GET /models` after task restart
- [ ] Write integration test for full model-sync flow

### Phase 5: Hardening

- [x] Add structured JSON logging (python-json-logger, job_id in every log)
- [x] Add CloudWatch custom metrics (queue depth, generation duration, error count)
- [x] Add job timeout / stale RUNNING job recovery
- [x] Create `api/workflows/img2img-sdxl/` template
- [x] Add `docker-compose.gpu.yml` override and README with curl examples

---

## v3: CloudFront Output Delivery

**Spec**: [spec-v3-cloudfront-output.md](spec-v3-cloudfront-output.md)

### Phase 1: CDK — CloudFront Distribution

- [ ] Add `CdnConstruct` in `infra/lib/constructs/cdn.ts` (distribution, OAC, key group)
- [ ] Lock down S3 bucket policy: deny direct `GetObject` on `outputs/*`, allow OAC principal only
- [ ] Store CloudFront private key PEM in SSM Parameter Store standard (`/comfy-aws/cloudfront-private-key`)
- [ ] Grant ECS task IAM role `ssm:GetParameter` on the key path

### Phase 2: API — Key Loading & URL Generation

- [ ] Add `cloudfront_domain`, `cloudfront_key_pair_id`, `cloudfront_private_key_ssm_path` to `config.py`
- [ ] Add `services/cdn.py`: fetch private key from SSM on startup, `generate_signed_url(s3_key, expires_in_seconds)`
- [ ] Write unit tests for `cdn.generate_signed_url()` using a fixed test RSA key pair (no AWS calls)

### Phase 3: API — Store Keys, Generate URLs at Request Time

- [ ] Update `dynamo.py`: store `output_keys: list[str]` instead of `output_urls`
- [ ] Update `models/job.py`: `output_urls` is computed at read time, not stored
- [ ] Update `routers/jobs.py` `GET /jobs/{id}`: generate signed URLs per key on each response

### Phase 4: Revocation Helper

- [ ] Add `.claude/scripts/revoke-output.sh` (s3 rm + CloudFront invalidation)
- [ ] Add `.claude/commands/revoke-output.md` slash command

---

## v4: API Key Authentication

**Spec**: [spec-v4-api-key-auth.md](spec-v4-api-key-auth.md)

### Phase 1: Middleware Implementation

- [x] Config: add `api_keys: str = ""` and `api_key_set` property to `config.py`
- [x] Implement `ApiKeyMiddleware` in `api/app/middleware/auth.py` (Starlette BaseHTTPMiddleware)
- [x] Wire middleware into `main.py`
- [x] Unit tests: `api/tests/test_auth_middleware.py` (no key, wrong key, valid key, disabled, /health exempt, multi-key)
- [x] Integration tests: auth behavior against running stack

### Phase 2: Docker + Deployment Wiring

- [x] Add `API_KEYS: ""` env var to `docker-compose.yml` api service
- [x] ECS task definition: pass `API_KEYS` from SSM `/comfy-aws/api-keys`
- [x] Update `CLAUDE.md` environment variable table with `API_KEYS` row

---

## v5: React Generation UI

**Spec**: [spec-v5-react-ui.md](spec-v5-react-ui.md)

### Phase 1: Project Scaffold

- [x] Initialize `frontend/` with Vite + React + TypeScript
- [x] Add Tailwind, Lucide React, clsx; configure Inter font
- [x] Configure Vite proxy (`/api` → `:8000`) in `vite.config.ts`
- [x] Validate `npm run dev` (port 5173) and `npm run build` (exits 0)

### Phase 2: Core UI Components

- [x] `Sidebar.tsx` — checkpoint, workflow, sampler, scheduler dropdowns with skeleton loaders
- [x] `PromptForm.tsx` — positive + negative textareas with character count
- [x] `SettingsPanel.tsx` — steps slider, CFG slider, seed input + randomize, width/height selects
- [x] `SubmitButton.tsx` — idle / loading / disabled states

### Phase 3: API Integration

- [x] `hooks/useApi.ts` — models + workflows fetch, shared `apiFetch` with `X-Api-Key` injection
- [x] `hooks/useJob.ts` — submission state machine, 2s polling until `COMPLETED`/`FAILED`
- [x] `ResultPanel.tsx` — image display, metadata row (duration, seed, checkpoint), download button
- [x] `ErrorBanner.tsx` — error display with "Try Again" reset

### Phase 4: Job History, Connection Status, and Polish

- [x] `hooks/useJobHistory.ts` — localStorage-persisted history, capped at 20 entries
- [x] `JobHistory.tsx` — thumbnail, status badge, relative timestamp per entry
- [x] `ConnectionStatus.tsx` — polls `GET /health` every 10s, green/red dot
- [x] `ApiKeyInput.tsx` — gear popover, saves to localStorage on blur
- [x] Responsive layout (single-column at 768px)
- [x] Mount `frontend/dist` as `StaticFiles` at `/ui` in FastAPI

---

## v2: Local E2E Generation Test

**Spec**: [spec-v2-local-e2e-test.md](spec-v2-local-e2e-test.md)

### Phase 1: Model Mount

- [x] Replace `comfyui-models` named volume with bind mount `./models:/app/models` in `docker-compose.yml`
- [x] Create `models/checkpoints/.gitkeep`, `models/loras/.gitkeep`, `models/vaes/.gitkeep` and gitignore model files

### Phase 2: E2E Test

- [x] Add `test_e2e_generation` to `api/tests/test_integration.py` — discovers checkpoint via `/object_info`, skips if none, submits with `steps=4, width=256, height=256`, polls to `COMPLETED`, verifies PNG bytes
- [x] Run test with a real checkpoint and confirm it passes end-to-end

---
