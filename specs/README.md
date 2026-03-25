# comfy-aws Specs

## Quick Status

| Version | Name | Progress | Status | Owner |
|---------|------|----------|--------|-------|
| v1 | ComfyUI on AWS | 0/25 | 📋 Draft | robert.w.seaton.jr@gmail.com |

---

## v1: ComfyUI on AWS

**Spec**: [spec-v1-comfy-aws.md](spec-v1-comfy-aws.md)

### Phase 1: API Foundation

- [ ] Initialize `api/` Python project (FastAPI, pydantic-settings, httpx, aioboto3, pytest-asyncio)
- [ ] Implement `config.py`, `models/job.py`, `models/workflow.py`
- [ ] Implement `services/workflow.py` (load, list, merge, validate)
- [ ] Create `api/workflows/txt2img-sdxl/` template (`workflow.json` + `schema.json`)
- [ ] Write and pass `tests/test_workflow.py` unit tests (no external deps)

### Phase 2: Local Dev Environment

- [ ] Create `docker/comfyui/Dockerfile` (CPU mode)
- [ ] Create `docker-compose.yml` (ComfyUI + FastAPI + LocalStack)
- [ ] Implement `app/comfy_client.py` (HTTP submit + WebSocket watch)
- [ ] Implement `services/dynamo.py` and `services/s3.py` with aioboto3
- [ ] Implement `services/job_service.py` (full async job lifecycle)
- [ ] Write and pass integration tests against live docker-compose stack

### Phase 3: CDK Infrastructure

- [ ] Initialize `infra/` CDK TypeScript project
- [ ] Implement `NetworkConstruct` (VPC, subnets, NAT, security groups)
- [ ] Implement `StorageConstruct` (S3 bucket, DynamoDB table)
- [ ] Implement `ComputeConstruct` (ECS cluster, ASG g4dn.xlarge Spot, EBS volumes)
- [ ] Implement `ServiceConstruct` (ECS task def with sidecar + init container, ALB)

### Phase 4: Model Management

- [ ] Define S3 key structure for model types
- [ ] Write model-sync init container script (`docker/model-sync/entrypoint.sh`)
- [ ] Upload test checkpoint to S3, verify in `GET /models` after task restart
- [ ] Write integration test for full model-sync flow

### Phase 5: Hardening

- [ ] Add structured JSON logging (python-json-logger, job_id in every log)
- [ ] Add CloudWatch custom metrics (queue depth, generation duration, error count)
- [ ] Add job timeout / stale RUNNING job recovery
- [ ] Create `api/workflows/img2img-sdxl/` template
- [ ] Add `docker-compose.gpu.yml` override and README with curl examples

---
