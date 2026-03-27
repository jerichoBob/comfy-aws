# comfy-aws Specs

## Quick Status

| Version | Name | Progress | Status | Owner |
|---------|------|----------|--------|-------|
| v1 | ComfyUI on AWS | 23/25 | 🔧 In Progress | robert.w.seaton.jr@gmail.com |
| v2 | Local E2E Generation Test | 4/4 | ✅ Complete | robert.w.seaton.jr@gmail.com |

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

## v2: Local E2E Generation Test

**Spec**: [spec-v2-local-e2e-test.md](spec-v2-local-e2e-test.md)

### Phase 1: Model Mount

- [x] Replace `comfyui-models` named volume with bind mount `./models:/app/models` in `docker-compose.yml`
- [x] Create `models/checkpoints/.gitkeep`, `models/loras/.gitkeep`, `models/vaes/.gitkeep` and gitignore model files

### Phase 2: E2E Test

- [x] Add `test_e2e_generation` to `api/tests/test_integration.py` — discovers checkpoint via `/object_info`, skips if none, submits with `steps=4, width=256, height=256`, polls to `COMPLETED`, verifies PNG bytes
- [x] Run test with a real checkpoint and confirm it passes end-to-end

---
