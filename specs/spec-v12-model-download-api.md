---
version: 12
name: model-download-api
display_name: "Model Download API"
status: pending
created: 2026-04-22
depends_on: [9]
tags: [api, models, ops]
---

# Model Download API

## Why (Problem Statement)

> Downloading a model from CivitAI or HuggingFace currently requires: download locally (slow, wastes bandwidth), upload to S3 (slow again), restart the ECS task to trigger model-sync. This spec adds `POST /admin/models/download` so the running instance pulls the model directly from the source — one hop instead of three, and the model is available in ComfyUI immediately without a restart.

### Context

- ComfyUI models live at `/data/models/{type}/` on the ECS instance (EBS volume, persists across task restarts but not instance termination)
- Models also need to be in S3 `models/{type}/` so the model-sync init container restores them on a fresh instance launch
- Large models (2–7 GB) are common — the download must stream to disk, not load into memory
- CivitAI requires an API token for authenticated downloads; HuggingFace requires a token for private/gated repos
- Provider tokens should be stored once in SSM and auto-applied by the API — callers should not need to pass tokens per-request
- The endpoint must be auth-guarded — it's an admin operation

---

## What (Requirements)

### User Stories

- **US-1**: As an operator, I want to POST a CivitAI or HuggingFace URL and have the model downloaded directly onto the running instance, available to ComfyUI immediately — without passing a token every time
- **US-2**: As an operator, I want to store my CivitAI and HuggingFace tokens once (in SSM) and have the API apply them automatically based on the download URL
- **US-3**: As an operator, I want to poll the download status so I know when it's safe to submit a job using the new model
- **US-4**: As an operator, I want the downloaded model automatically mirrored to S3 so it survives an instance restart

### Acceptance Criteria

- **AC-1**: `POST /admin/models/download` accepts `{url, type, filename?, token?}` and returns `{id, status: "downloading", type, filename}` within 500ms
- **AC-2**: The file is streamed (not buffered in memory) directly to `/data/models/{type}/{filename}`
- **AC-3**: `GET /admin/models/downloads/{id}` returns current status: `downloading | mirroring | ready | failed`
- **AC-4**: When download completes, the file is uploaded to `s3://$S3_BUCKET/models/{type}/{filename}` (background, non-blocking)
- **AC-5**: When status is `ready`, the model is immediately visible in `GET /models` without a ComfyUI restart
- **AC-6**: If `filename` is omitted, it is inferred from the `Content-Disposition` header or the URL path
- **AC-7**: The API auto-applies provider tokens from SSM: `civitai.com` URLs use `/comfy-aws/civitai-token`; `huggingface.co` URLs use `/comfy-aws/hf-token` — loaded at startup, applied as `Authorization: Bearer {token}`
- **AC-8**: If `token` is provided in the request body it overrides the SSM value for that request (escape hatch)
- **AC-9**: A failed download (404, auth error, disk full) sets status to `failed` with an `error` field explaining why
- **AC-10**: The endpoint requires `Authorization: Bearer` auth (same as all other endpoints); returns 401 otherwise
- **AC-11**: `GET /admin/models/` lists all models currently on disk by type (live filesystem read, not S3)
- **AC-12**: `sync-to-aws.sh --set-token civitai <token>` and `--set-token hf <token>` write to SSM as SecureString

### Out of Scope

- Progress percentage during download (streaming bytes-received tracking is a v2 concern)
- Multiple concurrent downloads (queue or reject if one is already in progress — single GPU instance, EBS I/O is the bottleneck)
- Model deletion via API
- CivitAI-specific URL parsing (user passes the direct download URL, including any `?token=` query param CivitAI uses, or uses the `token` field)

---

## How (Approach)

### Phase 1: Provider Token Loading

Add to `config.py`:

```python
civitai_token_ssm_path: str = "/comfy-aws/civitai-token"
hf_token_ssm_path: str = "/comfy-aws/hf-token"
```

Add `services/provider_tokens.py` — loaded at startup alongside `cdn.py`:

```python
_tokens: dict[str, str] = {}   # {"civitai": "...", "hf": "..."}

async def load_provider_tokens():
    """Fetch CivitAI and HF tokens from SSM. Missing = warn, don't fail."""
    for key, path in [("civitai", settings.civitai_token_ssm_path),
                      ("hf", settings.hf_token_ssm_path)]:
        try:
            _tokens[key] = await _fetch_ssm(path)
        except Exception:
            logger.warning("No token found at %s — unauthenticated downloads only", path)

def token_for_url(url: str) -> str | None:
    if "civitai.com" in url:
        return _tokens.get("civitai")
    if "huggingface.co" in url:
        return _tokens.get("hf")
    return None
```

### Phase 2: Download Service

Add `api/app/services/model_download.py`:

```python
@dataclass
class DownloadJob:
    id: str
    url: str
    type: str          # checkpoint | lora | vae
    filename: str
    status: str        # downloading | mirroring | ready | failed
    error: str | None
    started_at: datetime
    completed_at: datetime | None
    bytes_downloaded: int

_downloads: dict[str, DownloadJob] = {}   # in-memory, single-process

MODEL_DIRS = {
    "checkpoint": "/data/models/checkpoints",
    "lora":       "/data/models/loras",
    "vae":        "/data/models/vae",
}
```

`async def start_download(url, type, filename, token_override) -> DownloadJob`:
1. Reject with 409 if any job is currently `downloading` or `mirroring`
2. Resolve `token`: use `token_override` if provided, else `provider_tokens.token_for_url(url)`
3. Resolve `filename` from `Content-Disposition` or URL path if not provided
4. Create `DownloadJob` with status `downloading`, store in `_downloads`
5. Launch `asyncio.create_task(_run_download(job, token))`
6. Return job immediately

`async def _run_download(job, token)`:
1. Stream URL to `{MODEL_DIRS[type]}/{filename}` using `httpx.AsyncClient` with `stream()` — write chunks to disk
2. Send `Authorization: Bearer {token}` header if token is set
3. On completion: update `bytes_downloaded`, set status `mirroring`
4. Upload to S3: `await s3.upload_file(local_path, f"models/{type}/{filename}")`
5. Set status `ready`
6. On any exception: set status `failed`, store error message, delete partial file

**Disk path fallback for local dev:** `MODEL_DIRS` entries fall back to `./models/{type}` when `/data/models` doesn't exist (docker-compose bind mount). Detect at startup.

### Phase 3: Router

Add `api/app/routers/admin.py`:

```
POST /admin/models/download
  Body: { url, type, filename?, token? }
  Returns 202: DownloadJob

GET /admin/models/downloads/{id}
  Returns: DownloadJob (with current status)

GET /admin/models/downloads
  Returns: list of all DownloadJobs (most recent first)

GET /admin/models
  Returns: { checkpoints: [...], loras: [...], vaes: [...] }
  (Live filesystem read — same data as GET /models but without going through ComfyUI)
```

All routes require `Authorization: Bearer` (enforced by existing `ApiKeyMiddleware`).

Wire into `main.py`: `app.include_router(admin_router, prefix="/admin")`.

### Phase 4: sync-to-aws.sh Integration

Add two new modes to `sync-to-aws.sh`:

**`--set-token <provider> <token>`** — store a provider token in SSM as SecureString:
```bash
bash .claude/scripts/sync-to-aws.sh --set-token civitai <token>
bash .claude/scripts/sync-to-aws.sh --set-token hf <token>
```
Writes to `/comfy-aws/civitai-token` or `/comfy-aws/hf-token`. Prints confirmation (never echoes the token value).

**`--download <url> --type <type>`** — trigger a remote download via the API:
```bash
bash .claude/scripts/sync-to-aws.sh --download <url> --type checkpoint [--filename name.safetensors]
```
Implementation:
- POSTs to `http://$API_HOST:8000/admin/models/download` with `Authorization: Bearer $COMFY_API_KEY`
- Polls `GET /admin/models/downloads/{id}` every 5s until `ready` or `failed`
- Prints progress dots; on `ready` confirms the filename in `GET /models`

Requires `API_HOST` and `COMFY_API_KEY` in `~/.comfy-aws.env`.

### Phase 5: Tests

- **Unit**: `test_download_service.py` — `start_download()` with a local HTTP test server serving a small file; assert file lands in correct directory and status transitions to `ready`
- **Unit**: `test_filename_inference` — assert filename correctly extracted from `Content-Disposition: attachment; filename="model.safetensors"` and from URL path
- **Integration**: `test_admin_download_endpoint` — POST to `/admin/models/download` with a small public URL (e.g. a GitHub raw file); poll until `ready`; assert `GET /admin/models` lists the file
- **Integration**: `test_admin_models_list` — `GET /admin/models` returns dict with `checkpoints`, `loras`, `vaes` keys

---

## Technical Notes

### Why stream to disk, not buffer?

A 6 GB model can't fit in a Lambda/container memory budget even if ECS has it. `httpx.AsyncClient.stream()` pipes directly from the network socket to the file descriptor — constant memory regardless of model size.

### CivitAI auth

CivitAI supports two patterns:
- `?token=<api-key>` query param appended to the download URL
- `Authorization: Bearer <api-key>` header

The `token` field sends the Bearer header. If the user's CivitAI URL already includes `?token=`, no `token` field needed.

### HuggingFace auth

Public models: URL works as-is. Private/gated models: pass HF token in the `token` field. HuggingFace also accepts `Authorization: Bearer hf_...`.

### Single-download lock

Concurrent downloads to the same EBS volume would saturate I/O. If a download is already `in_progress`, reject new requests with `409 Conflict` and a message pointing to the in-progress job ID.

### S3 mirror timing

The S3 upload happens after the file is fully on disk — not concurrently with the download. The model is available to ComfyUI as soon as it's on disk (status `mirroring`), before the S3 upload completes. This means there's a brief window where the model is local but not yet in S3; acceptable for single-operator use.

---

## Open Questions

1. Should `GET /admin/models` hit the filesystem directly, or call ComfyUI's `/object_info`? Filesystem is faster and works even if ComfyUI is still loading; `/object_info` confirms ComfyUI actually sees the model.
2. Should the download job state persist across API restarts (DynamoDB)? Currently it's in-memory — a restart loses download history. Probably fine for ops use.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04-22 | Initial draft |
