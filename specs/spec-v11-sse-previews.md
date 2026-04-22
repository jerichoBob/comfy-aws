---
version: 11
name: sse-previews
display_name: "Live Step Previews via SSE"
status: pending
created: 2026-04-21
depends_on: [10]
tags: [api, frontend, comfyui]
---

# Live Step Previews via SSE

## Why (Problem Statement)

> KSampler denoises iteratively through latent space — each step is a partially-resolved image, smeared at first, sharpening into composition and then fine detail. Watching this convergence is one of the most compelling parts of diffusion models. The current API discards all intermediate frames and only returns the final image. This spec threads those preview frames from ComfyUI's WebSocket through a FastAPI SSE endpoint to the frontend in real time.

### What KSampler is actually doing

KSampler operates in **latent space**: a ~128×128×4 float tensor produced by the VAE encoder (not pixel space, not embedding space). At each step:

1. The UNet takes the current noisy latent + timestep + fixed CLIP text embeddings and predicts the noise component
2. The scheduler (Euler, DPM++, etc.) removes a calculated fraction of that predicted noise — advancing the latent along a probability gradient toward images that match the prompt
3. ComfyUI uses **TAESD** (Tiny AutoEncoder, ~4 MB) to quickly decode each intermediate latent to a pixel preview without running the full VAE — these JPEG thumbnails are emitted over the WebSocket as `b64_json` in `preview` messages

The CLIP text embeddings are a fixed conditioning signal — they act as a gravitational attractor in latent space. The sampler is integrating an ODE/SDE, not walking through embedding space.

### Context

- ComfyUI emits progress events over its WebSocket: `progress` (step N of total), `preview` (TAESD-decoded JPEG as base64), `executed` (done), `execution_error` (failed)
- The current `ComfyClient.watch_execution()` yields events until `executed`/`execution_error` but discards `progress` and `preview` messages
- After v10, the frontend can be running on a different machine — SSE is the right transport: unidirectional, works over plain HTTP, browser-native `EventSource`, no WebSocket upgrade required on the client side
- Preview image quality is intentionally low (TAESD JPEG ~256px) — that's fine; the point is convergence, not fidelity

---

## What (Requirements)

### User Stories

- **US-1**: As a user, I want to see the image taking shape step by step while the job is running, not just a spinner
- **US-2**: As a user, I want to see the step count (e.g. "12 / 30") alongside the preview so I know how far along the job is
- **US-3**: As a user, I want the final full-resolution output to replace the preview when the job completes — no jarring layout shift

### Acceptance Criteria

- **AC-1**: `GET /jobs/{id}/stream` is an SSE endpoint that emits events until the job reaches a terminal state
- **AC-2**: Each preview event contains `{ type: "preview", step: N, total: N, image_b64: "<jpeg>" }`
- **AC-3**: Each progress event (no image) contains `{ type: "progress", step: N, total: N }`
- **AC-4**: A completion event contains `{ type: "completed", output_urls: [...] }`
- **AC-5**: A failure event contains `{ type: "failed", error: "..." }`
- **AC-6**: The frontend replaces the spinner with the most recent preview frame as soon as the first preview arrives
- **AC-7**: The step counter `N / total` is visible below the preview image
- **AC-8**: When `type: "completed"` arrives, the full-resolution signed URL replaces the TAESD preview with no layout shift
- **AC-9**: If the SSE connection drops (network blip), the frontend reconnects automatically via `EventSource` retry behavior and re-subscribes from the current job state
- **AC-10**: The SSE endpoint is auth-guarded (same `Authorization: Bearer` check as all other endpoints)
- **AC-11**: For a job that has already completed when the SSE connection is opened, the endpoint immediately emits a single `completed` event and closes the stream

---

## How (Approach)

### Phase 1: ComfyClient — Capture Preview Frames

Extend `ComfyClient.watch_execution()` in `api/app/comfy_client.py`:

Currently yields `{"type": "executed" | "execution_error", ...}`. Extend to also yield:

```python
{"type": "progress", "step": int, "total": int}
{"type": "preview",  "step": int, "total": int, "image_b64": str}  # JPEG base64
```

ComfyUI WebSocket message structure for previews:

```json
{
  "type": "preview",
  "data": {
    "type": "preview",
    "image": "<base64-jpeg>"
  }
}
```

And for progress:

```json
{
  "type": "progress",
  "data": { "value": 12, "max": 30 }
}
```

Parse both and yield them upstream. Keep `watch_execution()` as a generator so callers can choose to consume or ignore intermediate events — `_watch_job` in `job_service.py` ignores them (no change needed there).

**TAESD prerequisite:** ComfyUI emits preview images only if `--preview-method taesd` (or `latent2rgb`) is passed at startup. Add this flag to:
- `docker-compose.yml` comfyui command: `python main.py --listen 0.0.0.0 --port 8188 --preview-method taesd`
- `infra/lib/constructs/service.ts` comfyui container command

### Phase 2: Preview Store in job_service

Add an in-memory preview buffer per job:

```python
# module-level dict, lives only for the lifetime of the process
_job_previews: dict[str, list[dict]] = {}
```

In `_watch_job`, for each `preview` or `progress` event yielded by `watch_execution()`, append to `_job_previews[job_id]`. Clear the buffer when the job reaches a terminal state (after a short delay to allow in-flight SSE clients to drain).

Expose two functions:
- `get_preview_events(job_id) -> list[dict]` — current buffer
- `subscribe_previews(job_id) -> AsyncGenerator` — yields events as they arrive (via `asyncio.Queue` per subscriber)

### Phase 3: SSE Endpoint

Add to `api/app/routers/jobs.py`:

```python
from fastapi.responses import StreamingResponse

@router.get("/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    """SSE stream of preview frames and terminal event for a job."""
    job = await dynamo.get_job(job_id)
    if not job:
        raise HTTPException(404)

    async def event_stream():
        # If already terminal, emit one event and close
        if job.status in ("COMPLETED", "FAILED", "CANCELLED"):
            yield _sse_event(_terminal_event(job))
            return

        # Stream live events
        async for event in job_service.subscribe_previews(job_id):
            yield _sse_event(event)
            if event["type"] in ("completed", "failed"):
                return
            if await request.is_disconnected():
                return

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx buffering if ever proxied
        },
    )

def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data)}\n\n"
```

Auth: SSE endpoint goes through the same `ApiKeyMiddleware` as all other routes — no special handling needed.

### Phase 4: Frontend — Live Preview Panel

Refactor the job result display in `ResultPanel.tsx` and `hooks/useJob.ts`:

**`useJob.ts` changes:**

- After job transitions to `polling` state (prompt submitted), open an `EventSource` to `GET /jobs/{id}/stream`
- Maintain state: `previewUrl: string | null`, `previewStep: number`, `previewTotal: number`
- On `preview` event: `URL.createObjectURL(base64ToBlob(event.image_b64, "image/jpeg"))` → set as `previewUrl`
- On `progress` event (no image): update step counters only
- On `completed` event: set `outputUrls` from `event.output_urls`, close `EventSource`, transition to `done`
- On `failed` event: set error, close `EventSource`, transition to `failed`
- On `EventSource` error: log, let browser auto-retry (default behavior)
- Clean up `EventSource` on unmount and on job reset

**`ResultPanel.tsx` changes:**

- While `status === "polling"`:
  - If `previewUrl` is set: show preview image + step counter `{previewStep} / {previewTotal}` below it + a subtle pulsing border to indicate "in progress"
  - If no preview yet: show the existing spinner
- On transition to `done`: swap `previewUrl` for the first `outputUrl` — use CSS `transition: opacity 0.3s` to crossfade, avoiding layout shift (both images same aspect ratio since TAESD preserves it)
- Revoke the preview blob URL (`URL.revokeObjectURL`) after the final image loads

### Phase 5: Tests

- **Unit**: `test_watch_execution_yields_previews` — mock ComfyUI WebSocket (via a real asyncio server in the test, not a mock object) that emits `progress` + `preview` + `executed` messages; assert generator yields all three event types in order
- **Integration**: `test_stream_endpoint_completed_job` — submit a job, wait for COMPLETED, then hit `/jobs/{id}/stream`; assert immediate `completed` event with output URLs
- **Integration**: `test_stream_endpoint_live` — with docker-compose running and a checkpoint present, submit an img2img or txt2img job and assert at least one `preview` event arrives before `completed`
- **Frontend**: Vitest + RTL — `useJob` hook with a real `EventSource` polyfill feeding mock SSE events; assert `previewUrl` updates on `preview` event; assert transition to `done` on `completed`

---

## Technical Notes

### TAESD vs latent2rgb

ComfyUI supports two preview methods:
- `latent2rgb` — fast approximation, no extra model, lower quality (color blobs)
- `taesd` — requires the TAESD model files (automatically downloaded by ComfyUI on first use, ~10 MB), much better quality showing actual structure

Use `taesd`. It downloads automatically; no manual model management needed.

### In-memory preview buffer limitations

`_job_previews` is a module-level dict — it's lost on process restart and not shared between processes. Since the ECS deployment runs one API container with one uvicorn worker (desired count 0/1, single EC2 instance), this is fine. If the API is ever scaled to multiple workers, replace with a Redis-backed pub/sub.

### SSE vs WebSocket for the client

SSE (`EventSource`) is unidirectional (server → client), which is all we need here. It:
- Works through HTTP proxies without special configuration
- Auto-reconnects by default
- Is trivial to implement server-side in FastAPI with `StreamingResponse`
- Does not require a WebSocket upgrade header (relevant for any future ALB/reverse-proxy setup)

### Memory cleanup

`_job_previews[job_id]` is cleared 30 seconds after terminal state to allow late-connecting SSE clients to still receive the final event. After that, the buffer is deleted. The `subscribe_previews` generator detects the terminal event and closes the queue.

### Preview frame size

TAESD previews are ~192×192 JPEG, ~5–15 KB each. At 30 steps, that's ~450 KB total per job over the stream — negligible.

---

## Open Questions

1. Should preview frames be stored anywhere (S3, DynamoDB) for jobs that are still running when the process restarts? Currently they're ephemeral — the frontend would just see a spinner until the next preview arrives after reconnect.

2. Should `generate.sh` (v10) support `--watch` to print step counts to stderr while polling? The SSE stream makes this natural but requires `curl --no-buffer` + `EventSource`-like logic in bash.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-04-21 | Initial draft |
