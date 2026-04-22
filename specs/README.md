# comfy-aws Specs

## Quick Status

| Version | Name                       | Progress | Status         | Owner                        |
| ------- | -------------------------- | -------- | -------------- | ---------------------------- |
| v1      | ComfyUI on AWS             | 24/25    | 🔧 In Progress | robert.w.seaton.jr@gmail.com |
| v2      | Local E2E Generation Test  | 4/4      | ✅ Complete    | robert.w.seaton.jr@gmail.com |
| v3      | CloudFront Output Delivery | 11/11    | ✅ Complete    | —                            |
| v4      | API Key Authentication     | 8/8      | ✅ Complete    | —                            |
| v5      | React Generation UI        | 15/15    | ✅ Complete    | —                            |
| v6      | Image Lightbox             | 8/8      | ✅ Complete    | robert.w.seaton.jr@gmail.com |
| v7      | Job Management             | 13/13    | ✅ Complete    | robert.w.seaton.jr@gmail.com |
| v8      | img2img + AWS Ops Toolkit  | 0/29     | 🔲 Pending     | robert.w.seaton.jr@gmail.com |
| v9      | Bearer Token Auth          | 8/8      | ✅ Complete    | —                            |
| v10     | Remote-First Deployment    | 0/15     | 🔲 Pending     | —                            |
| v11     | Live Step Previews via SSE | 0/11     | 🔲 Pending     | —                            |
| v12     | Model Download API         | 0/13     | 🔲 Pending     | —                            |

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
- [ ] Upload test checkpoint to S3, verify in `GET /models` after task restart <!-- BLOCKED: requires live AWS deployment — use .claude/scripts/test-model-sync-aws.sh -->
- [x] Write integration test for full model-sync flow

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

- [x] Add `CdnConstruct` in `infra/lib/constructs/cdn.ts` (distribution, OAC, key group)
- [x] Lock down S3 bucket policy: deny direct `GetObject` on `outputs/*`, allow OAC principal only
- [x] Store CloudFront private key PEM in SSM Parameter Store standard (`/comfy-aws/cloudfront-private-key`)
- [x] Grant ECS task IAM role `ssm:GetParameter` on the key path

### Phase 2: API — Key Loading & URL Generation

- [x] Add `cloudfront_domain`, `cloudfront_key_pair_id`, `cloudfront_private_key_ssm_path` to `config.py`
- [x] Add `services/cdn.py`: fetch private key from SSM on startup, `generate_signed_url(s3_key, expires_in_seconds)`
- [x] Write unit tests for `cdn.generate_signed_url()` using a fixed test RSA key pair (no AWS calls)

### Phase 3: API — Store Keys, Generate URLs at Request Time

- [x] Update `dynamo.py`: store `output_keys: list[str]` instead of `output_urls`
- [x] Update `models/job.py`: `output_urls` is computed at read time, not stored
- [x] Update `routers/jobs.py` `GET /jobs/{id}`: generate signed URLs per key on each response

### Phase 4: Revocation Helper

- [x] Add `.claude/scripts/revoke-output.sh` (s3 rm + CloudFront invalidation)
- [x] Add `.claude/commands/revoke-output.md` slash command

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

## v6: Image Lightbox

**Spec**: [spec-v6-image-lightbox.md](spec-v6-image-lightbox.md)

### Phase 1: Lightbox Component

- [x] Create `frontend/src/components/Lightbox.tsx` — portal-based full-screen overlay, centered image, backdrop click closes, ESC key closes
- [x] Add `overflow-hidden` to `<body>` while lightbox is open to trap scroll

### Phase 2: Wire Up ResultPanel

- [x] Add lightbox state to `ResultPanel.tsx`, wrap result image with click handler
- [x] Render `<Lightbox>` when image is clicked

### Phase 3: Wire Up JobHistory

- [x] Add `onImageClick?: (url: string) => void` prop to `JobHistory.tsx`
- [x] Wire click handler on thumbnails; lift lightbox state to `App.tsx`

### Phase 4: Tests

- [x] Vitest + React Testing Library: `Lightbox` renders with URL, ESC fires `onClose`, backdrop click fires `onClose`
- [x] Confirm `ResultPanel` and `JobHistory` click handlers open the lightbox (real DOM render, no mocks)

---

## v7: Job Management

**Spec**: [spec-v7-job-management.md](spec-v7-job-management.md)

### Phase 1: API — List and Cancel Endpoints

- [x] Add `GET /jobs` endpoint — queries DynamoDB GSI by status+created_at, limit 20, optional `?status=` filter
- [x] Add `POST /jobs/{id}/cancel` endpoint — sets status to CANCELLED, calls ComfyUI `/interrupt` if RUNNING
- [x] Add `dynamo.list_jobs(status, limit)` to `services/dynamo.py`
- [x] Integration tests for `GET /jobs` and `POST /jobs/{id}/cancel` against LocalStack

### Phase 2: Frontend — Active Jobs Hook

- [x] Add `hooks/useActiveJobs.ts` — polls `GET /jobs?status=RUNNING` every 3s, exposes list + `cancelJob(id)`
- [x] `cancelJob` calls `POST /jobs/{id}/cancel` with optimistic removal

### Phase 3: Frontend — Active Jobs UI

- [x] Active jobs section in right sidebar (above history, only visible when jobs are in-flight)
- [x] Each entry: status badge, truncated prompt, elapsed time, Cancel button with optimistic fade-out

### Phase 4: Frontend — Retry and Per-Entry Delete

- [x] Add Retry button to failed entries in `JobHistory.tsx` — resubmits with exact same params (including seed)
- [x] Wire `onRetry` prop from `App.tsx` → `JobHistory` → calls `submit()` with `entry.params`
- [x] Add per-entry delete button to `JobHistory.tsx` — removes single entry from localStorage history

### Phase 5: Tests

- [x] Integration: `GET /jobs` returns list filtered by status
- [x] Integration: `POST /jobs/{id}/cancel` transitions to CANCELLED
- [x] Frontend Vitest + RTL: active jobs renders, cancel triggers optimistic removal

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

## v9: Bearer Token Auth

**Spec**: [spec-v9-bearer-auth.md](spec-v9-bearer-auth.md)

### Phase 1: Middleware Update

- [x] Add `_extract_key()` to `ApiKeyMiddleware` — checks `Authorization: Bearer` first, falls back to `X-API-Key`
- [x] Reject 401 when `Authorization` header present with non-Bearer scheme and no `X-API-Key` fallback
- [x] Replace inline key extraction with `_extract_key()` call in `dispatch()`

### Phase 2: Frontend Update

- [x] Update `apiFetch()` in `hooks/useApi.ts` to send `Authorization: Bearer <key>` instead of `X-API-Key`

### Phase 3: Tests

- [x] `test_bearer_valid_key` — `Authorization: Bearer <key>` → 200
- [x] `test_bearer_invalid_key` — `Authorization: Bearer wrong` → 401
- [x] `test_bearer_wrong_scheme` — `Authorization: Basic <key>` → 401
- [x] `test_x_api_key_still_works` — existing `X-API-Key` header → 200 (regression)
- [x] `test_bearer_disabled_auth` — Bearer token with `API_KEYS=""` → 200

---
