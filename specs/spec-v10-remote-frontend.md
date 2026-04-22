---
version: 10
name: remote-frontend
display_name: "Remote-First Deployment"
status: pending
created: 2026-04-21
depends_on: [9]
tags: [frontend, infra, api, ops]
---

# Remote-First Deployment

## Why (Problem Statement)

> The GPU is expensive and slow to provision — it shouldn't also be serving React files. The frontend should run locally (dev server or static build) and talk to the API running in AWS over HTTPS. This also enables a CLI workflow: `generate.sh txt2img-sdxl --prompt "a red fox" --checkpoint model.safetensors` should fetch a PNG from wherever the API is running.

### Context

- Currently: frontend is built into the Docker image and served at `/ui` via FastAPI `StaticFiles`. Every frontend change requires a Docker rebuild + ECR push
- The Vite dev proxy (`/api → localhost:8000`) only works when the API is on the same machine
- The frontend injects `X-API-Key` (will become `Authorization: Bearer` after v9); the key is already stored in localStorage — it just needs a configurable API base URL to point at the AWS instance
- The ECS task currently uses host networking and exposes port 8000 directly with no TLS. For a single-operator deployment with API key auth, this is an acceptable risk if the security group is locked to known IPs; TLS via ACM + ALB is a future upgrade
- `GET /health` is always public — useful for monitoring without burning an API key

---

## What (Requirements)

### User Stories

- **US-1**: As a developer, I want to run the React UI locally with `npm run dev`, point it at the AWS API URL, and generate images without any Docker involvement
- **US-2**: As a developer, I want to run `generate.sh txt2img-sdxl --prompt "..." --checkpoint "..."` from my terminal and have a PNG saved locally
- **US-3**: As an operator, I want `manage.sh status` to print the API URL I should put in the frontend settings
- **US-4**: As an operator, I want the ECS security group locked to my current IP by default, with an easy way to update it

### Acceptance Criteria

- **AC-1**: FastAPI no longer mounts `frontend/dist` as `StaticFiles` — the `/ui` route is removed
- **AC-2**: FastAPI responds with correct CORS headers for requests from `http://localhost:5173` and any URL configured in `CORS_ORIGINS` env var
- **AC-3**: The frontend settings popover has an "API URL" field (alongside the existing API key field) stored in localStorage; all `apiFetch()` calls prepend this base URL
- **AC-4**: When API URL is set to the AWS instance, `npm run dev` works end-to-end: submit job → poll → display image
- **AC-5**: `generate.sh` accepts `--workflow`, `--output`, and `--<param> <value>` flags; polls until `COMPLETED`; saves the output image(s) to disk
- **AC-6**: `generate.sh --help` prints usage with examples
- **AC-7**: CDK `ComputeConstruct` security group allows port 8000 from a configurable CIDR (default `0.0.0.0/0` with a comment warning; can be overridden with `-c allowedCidr=<your-ip>/32` at deploy time)
- **AC-8**: `manage.sh status` prints the API URL in the format `http://<public-ip>:8000`

---

## How (Approach)

### Phase 1: Strip Frontend from FastAPI

- Remove the `app.mount("/ui", StaticFiles(...))` call from `api/app/main.py`
- Remove the `frontend/dist` build step from `api/Dockerfile` (the `COPY frontend/dist` line and any `npm run build` in the image build)
- Update `CLAUDE.md`: remove the "Build UI for FastAPI serving at /ui" step; replace with "Run locally with `npm run dev`"
- The `frontend/` directory and all its code stays — it just runs locally, not in AWS

### Phase 2: CORS Middleware

Add FastAPI CORS middleware to `api/app/main.py`:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,   # list parsed from CORS_ORIGINS env var
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)
```

Add to `config.py`:

```python
cors_origins: list[str] = Field(
    default=["http://localhost:5173", "http://localhost:4173"],
    description="Allowed CORS origins. Comma-separated string in env: CORS_ORIGINS",
)
```

Parse from env as a comma-separated string. In `docker-compose.yml`, set `CORS_ORIGINS=http://localhost:5173`.

### Phase 3: Frontend — Configurable API Base URL

- Add `apiUrl` to localStorage (key: `comfy-api-url`); default empty string = same-origin (local dev still works via Vite proxy with no config change)
- In `apiFetch()` in `hooks/useApi.ts`, prepend `apiUrl` to every request path when set
- In `ApiKeyInput.tsx` (the gear popover), add an "API URL" text input field above the key field
  - Placeholder: `http://1.2.3.4:8000`
  - Shows a green dot when the URL is reachable (reuse the `ConnectionStatus` health check logic)
- Vite proxy config: keep `proxy: { '/api': 'http://localhost:8000' }` in `vite.config.ts` — it only activates when API URL is empty, so local dev requires zero config

### Phase 4: CLI Client

Create `.claude/scripts/generate.sh`:

```
Usage: generate.sh --workflow <id> [--output <path>] [--param key=value ...]

Required env vars (or ~/.comfy-aws.env):
  COMFY_API_URL    e.g. http://1.2.3.4:8000
  COMFY_API_KEY    the bearer token

Options:
  --workflow <id>           workflow ID (e.g. txt2img-sdxl)
  --output <file|dir>       where to save the output PNG (default: ./<job_id>.png)
  --param key=value         any number of workflow params (repeatable)
  --poll-interval <sec>     default 3
  --timeout <sec>           default 300
  --help                    print this message

Examples:
  generate.sh \
    --workflow txt2img-sdxl \
    --param checkpoint=sd_xl_base_1.0.safetensors \
    --param positive_prompt="a red fox in a snowy forest" \
    --param steps=30 \
    --output ./fox.png

Exit codes: 0 = success, 1 = job failed, 2 = timeout, 3 = auth error
```

Implementation:

- Pure bash + `curl` + `jq` (both available on macOS by default)
- `POST /jobs` with JSON body built from `--param` flags
- Polls `GET /jobs/{id}` every `--poll-interval` seconds until `COMPLETED` or `FAILED`
- Downloads output image from the returned signed URL via `curl -L -o <output>`
- Progress indicator: prints `step N/total` if the job exposes it (future SSE integration point)

### Phase 5: CDK — Security Group + Stack Outputs

In `infra/lib/constructs/network.ts` (or wherever the API security group is defined):

- Add a CDK context variable `allowedCidr` (default `0.0.0.0/0`):
  ```ts
  const allowedCidr = this.node.tryGetContext("allowedCidr") ?? "0.0.0.0/0";
  apiSg.addIngressRule(Peer.ipv4(allowedCidr), Port.tcp(8000), "API access");
  ```
- Deploy with `-c allowedCidr=$(curl -s https://checkip.amazonaws.com)/32` to lock to your current IP

In `infra/lib/comfy-aws-stack.ts`, add `CfnOutput` entries:

```ts
new CfnOutput(this, "ClusterName", { value: compute.cluster.clusterName });
new CfnOutput(this, "ServiceName", { value: service.ecsService.serviceName });
new CfnOutput(this, "BucketName", { value: storage.bucket.bucketName });
new CfnOutput(this, "TableName", { value: storage.table.tableName });
```

These are consumed by `manage.sh` (v8) via `aws cloudformation describe-stacks`.

### Phase 6: Tests

- **Unit**: `test_cors_headers` — `OPTIONS /jobs` with `Origin: http://localhost:5173` returns `Access-Control-Allow-Origin`
- **Unit**: `test_no_ui_route` — `GET /ui` returns 404 (route removed)
- **Manual verification checklist** (documented in spec):
  - [ ] `npm run dev` with `COMFY_API_URL` pointing at a running AWS task → submit job → image appears
  - [ ] `generate.sh --workflow txt2img-sdxl ...` → PNG saved locally
  - [ ] Request from unknown origin blocked by CORS (browser devtools shows error)
  - [ ] `manage.sh status` prints public IP

---

## Technical Notes

### Why not TLS in this spec?

An ALB with ACM cert adds ~$20/month (ALB) + domain requirement. For a single-operator deployment with API key auth and IP-restricted security groups, HTTP is acceptable. Add TLS when the deployment becomes multi-user or the API URL needs to be shared. Flag in `manage.sh status` output: `⚠ HTTP only — traffic is unencrypted`.

### Vite proxy compatibility

When `apiUrl` is empty in localStorage, `apiFetch()` sends requests to `/api/...` which the Vite dev proxy forwards to `localhost:8000`. This means local dev (docker-compose) requires zero frontend config — same experience as before. Setting `apiUrl` activates remote mode.

### `generate.sh` and `manage.sh` relationship

`generate.sh` is a user-facing generation client. `manage.sh` is an operator tool. They share `~/.comfy-aws.env` for credentials but serve different purposes. `generate.sh` has no dependency on `manage.sh`.

---

## Open Questions

1. Should `generate.sh` support `--workflow img2img-sdxl` with `--param image=@path/to/file.png` (read file, base64-encode, pass as data URI)? This would make img2img usable from the CLI without a browser.

2. Should the security group default to `0.0.0.0/0` with a warning, or require `-c allowedCidr=` to be explicit? Requiring explicit CIDR is safer but adds friction for new deployments.

---

## Changelog

| Date       | Change        |
| ---------- | ------------- |
| 2026-04-21 | Initial draft |
