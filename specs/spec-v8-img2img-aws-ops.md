---
version: 8
name: img2img-aws-ops
display_name: "img2img + AWS Ops Toolkit"
status: pending
created: 2026-04-21
depends_on: [7]
tags: [api, frontend, infra, ops]
---

# img2img + AWS Ops Toolkit

## Why (Problem Statement)

> The img2img workflow exists in schema + code but has a type mismatch that prevents it from working. Beyond that, the project has no tooling for day-to-day AWS operations — spinning the instance up and down, getting logs, downloading models, or adding new workflows all require manual `aws` CLI commands spread across the project. This spec closes both gaps.

### Context

**img2img gap:** `comfy_client.upload_image()` and `_upload_image_params()` were added (uncommitted) but the `img2img-sdxl/schema.json` declares the `image` param as `type: "string"` — the upload logic only triggers on `type: "image"`. Nothing works end-to-end yet. The frontend also has no image upload UI; it only renders text inputs and sliders.

**Ops gap:**

- Scaling the ECS service up/down requires manual `aws ecs update-service` commands
- Getting logs requires looking up CloudWatch log group names from CDK output
- Uploading a new model checkpoint is: copy to S3, restart the task, wait for sync — no script wraps this
- Adding a new workflow requires rebuilding + pushing the Docker image just to add two JSON files
- There's no way to download a model from a URL (HuggingFace, CivitAI) directly into the running instance without SSHing in

**Custom nodes:** The Comfyroll node pack was added to the Dockerfile but none of the current workflows use it. The Dockerfile change should be justified or reverted; any future workflows that use Comfyroll need to be documented here.

---

## What (Requirements)

### User Stories

- **US-1**: As a user, I want to upload a source image in the UI and run img2img, getting a transformed output image
- **US-2**: As an operator, I want `manage.sh up` / `manage.sh down` to start/stop the GPU instance without memorizing ECS commands
- **US-3**: As an operator, I want `manage.sh logs api` to tail the FastAPI container logs in real time
- **US-4**: As an operator, I want `manage.sh model upload checkpoint ./my-model.safetensors` to put a model in S3 and trigger a sync
- **US-5**: As an operator, I want `manage.sh model download checkpoint <url> <filename>` to pull a model from HuggingFace/CivitAI onto the running instance
- **US-6**: As an operator, I want to add or update a workflow template without rebuilding the Docker image
- **US-7**: As an operator, I want `manage.sh workflow push ./my-workflow/` to publish a workflow to S3 and have it appear in the API immediately

### Acceptance Criteria

- **AC-1**: Submitting an img2img job with a base64-encoded PNG completes with `COMPLETED` status and returns a signed output URL
- **AC-2**: The frontend detects `type: "image"` params from the workflow schema and renders a drag-and-drop / click-to-upload image input
- **AC-3**: The uploaded source image is shown as a small preview alongside the output in ResultPanel
- **AC-4**: `manage.sh status` prints ECS service desired/running count and the public IP of the running task (if any)
- **AC-5**: `manage.sh up` / `manage.sh down` set desired count to 1 / 0 and print confirmation
- **AC-6**: `manage.sh logs [api|comfyui]` tails the corresponding CloudWatch log stream
- **AC-7**: `manage.sh exec [api|comfyui] [cmd]` runs a command in the named container via ECS Exec
- **AC-8**: `manage.sh model upload <type> <filepath>` uploads to `s3://$S3_BUCKET/models/<type>/<filename>` and prints the key
- **AC-9**: `manage.sh model download <type> <url> <filename>` downloads to the running instance and mirrors to S3
- **AC-10**: `manage.sh model list [type]` lists available models in S3 by type
- **AC-11**: `manage.sh model sync` restarts the ECS task to re-run the model-sync init container
- **AC-12**: S3-backed workflows at `s3://$S3_BUCKET/workflows/<id>/` are loaded by the API on startup (merged with bundled templates, S3 wins on conflict)
- **AC-13**: `manage.sh workflow push <dir>` uploads workflow + schema JSON to S3 and hot-reloads via `POST /admin/workflows/reload`
- **AC-14**: `manage.sh workflow list` shows bundled and S3-backed workflows with source label
- **AC-15**: `manage.sh workflow pull <id> [dir]` downloads a workflow from S3 to a local directory

### Out of Scope

- Multi-image batch img2img (single image input only)
- Inpainting / masking (separate workflow concern)
- HuggingFace token management (user provides pre-authenticated download URL or token via env var)
- Workflow versioning / rollback
- Frontend workflow authoring (JSON editor in the UI)

---

## How (Approach)

### Phase 1: img2img Hardening

**Fix the type mismatch and commit existing work:**

- In `api/workflows/img2img-sdxl/schema.json`, change the `image` param's `type` from `"string"` to `"image"` — this activates the `_upload_image_params` upload path in `job_service.py`
- Add `sampler` and `scheduler` params to `img2img-sdxl/schema.json` (nodes `10` inputs `sampler_name` / `scheduler`), consistent with txt2img
- Commit the three uncommitted files (`comfy_client.py`, `job_service.py`, `docker/comfyui/Dockerfile`) together with the schema fix
- Clarify or revert the Comfyroll node pack: if it's needed for a planned workflow, document it; if not, remove the `git clone` from the Dockerfile to keep the image lean

**Cleanup: purge uploaded input images after job completion**

- After `_watch_job` downloads and uploads outputs to S3, call a new `ComfyClient.delete_input_image(filename)` that hits ComfyUI's `DELETE /upload/image/{filename}` or falls back to a no-op if that endpoint doesn't exist — prevents `/app/input/` from accumulating garbage across jobs

**Integration test:**

- `test_img2img_job` in `tests/test_integration.py` — loads a small 64×64 PNG, encodes to base64 data URI, submits `img2img-sdxl` job, asserts `COMPLETED` with output key (skips if no checkpoint present)

---

### Phase 2: Frontend — Image Upload for img2img

**Schema-driven image input:**

- Update `hooks/useApi.ts` to expose raw `schema.params` per workflow alongside the existing workflow list
- Add `ImageUpload.tsx` — drag-and-drop + click-to-select, shows a thumbnail preview of the chosen image, encodes the file as a base64 data URI on selection, calls `onChange(dataUri)` upward
- In `SettingsPanel.tsx`, for each param with `type === "image"`, render `<ImageUpload>` instead of a text input; store the data URI in the form params map keyed by param name
- `SubmitButton` stays disabled until all required `image` params have a value

**Result display:**

- In `ResultPanel.tsx`, when the current job's workflow is img2img, show the source image (thumbnail from the submitted param) to the left of the output image so users can compare

**Validation:**

- Display a warning (reuse the existing param-validation banner) if the user switches to img2img workflow without setting the image param

---

### Phase 3: AWS Management CLI

**`.claude/scripts/manage.sh`** — bash script, reads config from environment or prompts:

```
Required env vars (or ~/.comfy-aws.env):
  AWS_PROFILE         AWS profile to use
  AWS_REGION          e.g. us-east-1
  ECS_CLUSTER         from CDK output: ComfyAwsStack.ClusterName
  ECS_SERVICE         from CDK output: ComfyAwsStack.ServiceName
  S3_BUCKET           from CDK output: ComfyAwsStack.BucketName
  DYNAMO_TABLE        from CDK output: ComfyAwsStack.TableName
  LOG_GROUP_API       /comfy-aws/ecs/api
  LOG_GROUP_COMFYUI   /comfy-aws/ecs/comfyui
```

**Subcommands:**

| Command                               | Action                                                                              |
| ------------------------------------- | ----------------------------------------------------------------------------------- |
| `manage.sh status`                    | `aws ecs describe-services` + `aws ec2 describe-instances` for public IP            |
| `manage.sh up`                        | `aws ecs update-service --desired-count 1`                                          |
| `manage.sh down`                      | `aws ecs update-service --desired-count 0`                                          |
| `manage.sh logs [api\|comfyui] [-f]`  | `aws logs tail` with optional `--follow`                                            |
| `manage.sh exec [api\|comfyui] [cmd]` | `aws ecs execute-command` (requires ECS Exec enabled — already set in `service.ts`) |
| `manage.sh deploy`                    | Wraps existing `cfn-deploy.sh`                                                      |

**CDK stack outputs:** Add `CfnOutput` entries to `ComfyAwsStack` for `ClusterName`, `ServiceName`, `BucketName`, `TableName` so `manage.sh` can auto-resolve them:

```bash
# manage.sh can call:
aws cloudformation describe-stacks --stack-name ComfyAwsStack \
  --query 'Stacks[0].Outputs' to populate its vars automatically
```

---

### Phase 4: Model Management

**Extend `manage.sh` with `model` subcommand:**

```bash
manage.sh model upload <type> <filepath>
# Validates type in {checkpoints,loras,vaes,vae}
# aws s3 cp <filepath> s3://$S3_BUCKET/models/<type>/<basename>
# Prints S3 key + suggests `manage.sh model sync` to pull it down

manage.sh model list [type]
# aws s3 ls s3://$S3_BUCKET/models/<type>/ (or all types if omitted)
# Annotates with file size + last modified

manage.sh model download <type> <url> <filename>
# If instance is running:
#   manage.sh exec comfyui "wget -O /app/models/<type>/<filename> '<url>'"
#   Then: aws s3 cp s3://$S3_BUCKET/models/<type>/<filename> ... (mirror back)
# If instance is down:
#   Runs wget locally or via a one-shot ECS Fargate task (future; for now: fail with guidance)

manage.sh model sync
# Stops the running task (ECS replaces it, re-running init container)
# Polls until new task is RUNNING + API health check passes
```

**S3 → local path convention:** type `vaes` and `vae` both map to `s3://bucket/models/vae/` (normalise in the script).

---

### Phase 5: Dynamic Workflows

**S3-backed workflow loader (API side):**

- Add `load_s3_workflows()` in `services/workflow.py` — called at startup:
  - Lists `s3://$S3_BUCKET/workflows/` prefix
  - For each `<id>/workflow.json` + `<id>/schema.json` pair, loads into the in-memory workflow registry
  - S3 entries shadow bundled templates with the same ID
  - Skips gracefully if `S3_BUCKET` is unset (local dev without bucket)
- Add `POST /admin/workflows/reload` (auth-guarded) — re-runs `load_s3_workflows()` and returns updated workflow list; used by `manage.sh workflow push` after upload

**`manage.sh workflow` subcommand:**

```bash
manage.sh workflow list
# GET /workflows (via localhost on running instance) or direct S3 listing
# Marks each as [bundled] or [s3]

manage.sh workflow push <dir>
# Validates dir contains workflow.json + schema.json
# Infers workflow ID from dirname
# aws s3 cp <dir>/workflow.json s3://$S3_BUCKET/workflows/<id>/workflow.json
# aws s3 cp <dir>/schema.json  s3://$S3_BUCKET/workflows/<id>/schema.json
# If instance is running: calls POST /admin/workflows/reload

manage.sh workflow pull <id> [output-dir]
# aws s3 cp --recursive s3://$S3_BUCKET/workflows/<id>/ <output-dir>/<id>/
```

**Local dev:** `load_s3_workflows()` is called but skipped when `AWS_ENDPOINT_URL` (LocalStack) is set and bucket doesn't have a `workflows/` prefix yet — logs a warning but doesn't fail startup.

---

### Phase 6: Tests

- **Integration (img2img):** `test_img2img_job` — base64 PNG → COMPLETED + output key (skip if no checkpoint)
- **Integration (workflow reload):** `test_workflow_reload` — upload a minimal schema to LocalStack S3 `workflows/` prefix, hit `/admin/workflows/reload`, assert new workflow appears in `GET /workflows`
- **Unit (manage.sh):** `bats` test or manual run guide for each subcommand against LocalStack + a `docker-compose`-local ECS-lite (out of scope for automated CI; document manual verification steps)
- **Frontend (image upload):** Vitest + RTL — `ImageUpload` renders, file drop triggers `onChange` with data URI; `SubmitButton` disabled without image; switches enabled once image selected

---

## Technical Notes

### Architecture Decisions

- **`manage.sh` over Python CLI**: bash is zero-dependency, directly wraps the `aws` CLI, and is readable by everyone. If it grows beyond ~300 lines, migrate to a Typer-based Python tool in `.claude/scripts/manage.py`.
- **`POST /admin/workflows/reload` vs restart**: Hot-reload avoids a 2-5 minute task restart for workflow changes. It's auth-guarded (X-API-Key required) and only available to operators who already have the key.
- **S3 workflow loading at startup vs request time**: Startup loading keeps request latency flat. The reload endpoint is the escape hatch for pushing a new workflow without restarting.
- **`delete_input_image` cleanup**: ComfyUI's REST API may not expose a delete endpoint depending on version. Implement as best-effort; log a warning if it fails, never raise.
- **Comfyroll nodes**: If being kept, document the specific nodes used and which planned workflow requires them. If no planned workflow requires them within this spec, remove from Dockerfile — the image build takes longer and the nodes (~300 MB) bloat the image for no benefit.

### Dependencies

| Dependency                   | Notes                                                                           |
| ---------------------------- | ------------------------------------------------------------------------------- |
| ECS Exec enabled             | Already set in `service.ts` (`enableExecuteCommand: true`)                      |
| AWS CLI v2                   | Required locally for `manage.sh`; already used in `cfn-deploy.sh`               |
| bats-core (optional)         | For `manage.sh` unit tests                                                      |
| CloudFormation outputs       | CDK stack must export cluster/service/bucket names                              |
| ComfyUI input folder cleanup | ComfyUI version must support DELETE on `/upload/image` or a custom cleanup path |

### Risks & Mitigations

| Risk                                                | Mitigation                                                                                                                                                                                                                                                                    |
| --------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `manage.sh model download` needs a running instance | Fail with clear message: "Scale up with `manage.sh up` first"; future: Fargate task                                                                                                                                                                                           |
| S3 workflow JSON malformed — crashes API startup    | Catch and skip per-workflow; log warning, don't fail the entire startup                                                                                                                                                                                                       |
| Hot-reload races with in-flight jobs                | In-memory registry is read-only at request time; reload swaps atomically (dict replace) — no lock needed for CPython's GIL                                                                                                                                                    |
| Comfyroll install doubles build time                | Evaluate whether it's actually needed before shipping                                                                                                                                                                                                                         |
| ECS Exec requires SSM agent in container            | Base ComfyUI image is Ubuntu; SSM agent is NOT installed by default. The `AmazonSSMManagedInstanceCore` policy is on the instance role, but the container needs the agent too. Either install in Dockerfile or use `exec` via the instance directly (SSH via SSM on the host) |

### ECS Exec Note

ECS Exec injects the SSM session manager plugin via the ECS agent on the host — it does NOT require the SSM agent to be installed inside the container. The only requirements are: `enableExecuteCommand: true` on the service (already set), and the task role has `ssmmessages:*` permissions (add to `service.ts`).

---

## Open Questions

1. **Comfyroll nodes** — which specific nodes are planned, and in which future workflow? If the answer is "not sure yet," remove from Dockerfile and re-add when the workflow is ready.

2. **`manage.sh model download` offline path** — when the instance is down, should `download` spin up a one-shot ECS Fargate task to pull the model, or just fail? Fargate approach is cleaner (no GPU needed for a wget) but adds CDK complexity.

3. **Workflow ID namespace** — should S3 workflow IDs be prefixed to avoid collision with bundled ones (e.g. `custom/inpaint-sdxl`)? Or is the "S3 wins on conflict" rule sufficient?

4. **Frontend workflow switching UX** — when the user changes the workflow dropdown from txt2img to img2img, should the image upload slot appear inline in the settings panel, or as a separate step before the prompt?

---

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-04-21 | Initial draft |
