---
version: 2
name: local-e2e-test
display_name: "Local E2E Generation Test"
status: draft
created: 2026-03-26
depends_on: [1]
tags: [testing, local-dev, comfyui]
---

# Local E2E Generation Test

## Why (Problem Statement)

> As a developer, I want to verify that the full image generation pipeline works locally before deploying to AWS so that I can catch bugs early and avoid wasted deploy cycles.

### Context

- The existing integration tests only verify API surface (submit job, check immediate response) — they don't wait for generation to complete or verify an image is returned
- The ComfyUI container's model directory is a named Docker volume, so models don't persist across rebuilds and can't be loaded by dropping files on disk
- Without a real checkpoint, the generation path is untested locally — the service could be deployed to AWS with broken workflow logic and only fail under real load
- CPU generation is slow but works for local dev; using small dimensions (256×256) and few steps (4) keeps it fast enough to be useful

---

## What (Requirements)

### Acceptance Criteria

- AC-1: `./models/` bind-mounted into ComfyUI container at `/app/models` — models dropped there persist across container restarts and rebuilds
- AC-2: `./models/` gitignored (except `.gitkeep`) so checkpoints aren't committed
- AC-3: `test_e2e_generation` queries ComfyUI `GET /object_info` to discover available checkpoints; skips with a clear message if none found
- AC-4: Test submits a txt2img job with `steps=4`, `width=256`, `height=256` and the first available checkpoint
- AC-5: Test polls `GET /jobs/{id}` until status is `COMPLETED` or a 10-minute timeout, failing with a descriptive error on timeout
- AC-6: On `COMPLETED`, asserts `output_urls` is non-empty
- AC-7: Fetches the first `output_url` and asserts the response is valid PNG bytes (magic bytes `\x89PNG`)

### Out of Scope

- Downloading a model as part of setup — user must supply the checkpoint
- Testing img2img workflow end-to-end (covered by same pattern if needed later)
- GPU acceleration (CPU-only for local dev)

---

## How (Approach)

### Phase 1: Model Mount

- Replace `comfyui-models` named volume in `docker-compose.yml` with bind mount `./models:/app/models`
- Create `models/checkpoints/.gitkeep`, `models/loras/.gitkeep`, `models/vaes/.gitkeep`
- Add `models/` to `.gitignore` except `.gitkeep` files
- Remove `comfyui-models` from the `volumes:` section at bottom of `docker-compose.yml`

### Phase 2: E2E Test

- Add `test_e2e_generation` to `api/tests/test_integration.py`
- Discover checkpoints: `GET http://localhost:8188/object_info` → parse `CheckpointLoaderSimple.input.required.ckpt_name[0]`
- Skip if list is empty: `pytest.skip("No checkpoints in models/checkpoints — drop a .safetensors file to run this test")`
- Submit job: `POST /jobs` with `workflow_id=txt2img-sdxl`, `steps=4`, `width=256`, `height=256`, `seed=42`, `checkpoint=checkpoints[0]`
- Poll loop: every 5s, `GET /jobs/{id}`, break on `COMPLETED` or `FAILED`, fail after 600s
- Assert `status == "COMPLETED"`
- Assert `len(output_urls) > 0`
- Fetch `output_urls[0]`, assert `response.content[:4] == b'\x89PNG'`

---

## Technical Notes

### Dependencies

- ComfyUI must be running (`docker compose up -d`)
- At least one `.safetensors` checkpoint in `./models/checkpoints/`
- `httpx` (already in test deps)

### Risks & Mitigations

| Risk                                                    | Mitigation                                                                          |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| CPU generation exceeds 10-min timeout                   | Use `steps=4`, `width=256`, `height=256`; document expected time                    |
| LocalStack presigned URLs don't return real image bytes | Fetch the URL and check PNG magic bytes — will catch if S3 upload/presign is broken |
| ComfyUI object_info schema changes                      | Pin ComfyUI version in Dockerfile                                                   |

---

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-03-26 | Initial draft |
