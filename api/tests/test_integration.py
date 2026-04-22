"""Integration tests — require docker compose up (ComfyUI + LocalStack)."""
import os
import subprocess

import httpx
import pytest

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://localhost:8188")
LOCALSTACK_ENDPOINT = os.environ.get("AWS_ENDPOINT_URL", "http://localhost:4566")
LOCALSTACK_BUCKET = os.environ.get("S3_BUCKET", "comfy-aws-local")
_LOCALSTACK_ENV = {
    **os.environ,
    "AWS_ACCESS_KEY_ID": os.environ.get("AWS_ACCESS_KEY_ID", "test"),
    "AWS_SECRET_ACCESS_KEY": os.environ.get("AWS_SECRET_ACCESS_KEY", "test"),
    "AWS_DEFAULT_REGION": os.environ.get("AWS_DEFAULT_REGION", "us-east-1"),
}


def _api_available() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _comfyui_available() -> bool:
    try:
        r = httpx.get(f"{COMFYUI_URL}/system_stats", timeout=5)
        return r.status_code == 200
    except Exception:
        return False


def _localstack_available() -> bool:
    try:
        r = httpx.get(f"{LOCALSTACK_ENDPOINT}/_localstack/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _api_available(),
    reason="API not reachable — run docker compose up first",
)


def test_health_ok():
    r = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


def test_list_workflows():
    r = httpx.get(f"{BASE_URL}/workflows", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert "txt2img-sdxl" in data["workflows"]


def test_get_workflow_schema():
    r = httpx.get(f"{BASE_URL}/workflows/txt2img-sdxl", timeout=10)
    assert r.status_code == 200
    data = r.json()
    assert data["id"] == "txt2img-sdxl"
    assert "positive_prompt" in data["params"]


def test_get_workflow_not_found():
    r = httpx.get(f"{BASE_URL}/workflows/does-not-exist", timeout=10)
    assert r.status_code == 404


def test_submit_job_invalid_workflow():
    r = httpx.post(
        f"{BASE_URL}/jobs",
        json={"workflow_id": "nonexistent", "params": {}},
        timeout=10,
    )
    assert r.status_code == 404


def test_submit_job_missing_params():
    r = httpx.post(
        f"{BASE_URL}/jobs",
        json={"workflow_id": "txt2img-sdxl", "params": {}},
        timeout=10,
    )
    assert r.status_code == 422


@pytest.mark.skipif(not _comfyui_available(), reason="ComfyUI not reachable")
def test_submit_and_poll_job():
    r = httpx.post(
        f"{BASE_URL}/jobs",
        json={
            "workflow_id": "txt2img-sdxl",
            "params": {
                "positive_prompt": "a red apple",
                "checkpoint": "v1-5-pruned-emaonly.safetensors",
            },
        },
        timeout=30,
    )
    assert r.status_code == 202
    job = r.json()
    assert "id" in job
    assert job["status"] in ("PENDING", "RUNNING")

    # Poll status
    job_id = job["id"]
    status_r = httpx.get(f"{BASE_URL}/jobs/{job_id}", timeout=10)
    assert status_r.status_code == 200
    assert status_r.json()["id"] == job_id


def test_get_job_not_found():
    r = httpx.get(f"{BASE_URL}/jobs/00000000-0000-0000-0000-000000000000", timeout=10)
    assert r.status_code == 404


def _available_checkpoints() -> list[str]:
    """Query ComfyUI object_info for available checkpoints."""
    try:
        r = httpx.get(f"{COMFYUI_URL}/object_info/CheckpointLoaderSimple", timeout=5)
        if r.status_code != 200:
            return []
        data = r.json()
        return data.get("CheckpointLoaderSimple", {}) \
                   .get("input", {}) \
                   .get("required", {}) \
                   .get("ckpt_name", [None])[0] or []
    except Exception:
        return []


@pytest.mark.skipif(not _comfyui_available(), reason="ComfyUI not reachable")
def test_e2e_generation():
    checkpoints = _available_checkpoints()
    if not checkpoints:
        pytest.skip(
            "No checkpoints found in models/checkpoints/ — "
            "drop a .safetensors file there and restart ComfyUI to run this test"
        )

    checkpoint = checkpoints[0]

    # Submit job with small dimensions and few steps to keep CPU time reasonable
    r = httpx.post(
        f"{BASE_URL}/jobs",
        json={
            "workflow_id": "txt2img-sdxl",
            "params": {
                "positive_prompt": "a red apple on a white background",
                "checkpoint": checkpoint,
                "steps": 4,
                "width": 256,
                "height": 256,
                "seed": 42,
            },
        },
        timeout=30,
    )
    assert r.status_code == 202, f"Submit failed: {r.text}"
    job_id = r.json()["id"]

    # Poll until COMPLETED or timeout (10 minutes for CPU generation)
    import time
    deadline = time.time() + 600
    status = None
    while time.time() < deadline:
        poll = httpx.get(f"{BASE_URL}/jobs/{job_id}", timeout=10)
        assert poll.status_code == 200
        job = poll.json()
        status = job["status"]
        if status in ("COMPLETED", "FAILED"):
            break
        time.sleep(5)
    else:
        pytest.fail(f"Job {job_id} did not complete within 10 minutes (last status: {status})")

    assert status == "COMPLETED", f"Job failed with status: {status}"

    output_urls = r.json().get("output_urls") or httpx.get(f"{BASE_URL}/jobs/{job_id}", timeout=10).json().get("output_urls", [])
    assert len(output_urls) > 0, "No output_urls on completed job"

    # Fetch the image and verify it's a valid PNG
    img_r = httpx.get(output_urls[0], timeout=30, follow_redirects=True)
    assert img_r.status_code == 200, f"Failed to fetch output URL: {img_r.status_code}"
    assert img_r.content[:4] == b"\x89PNG", "Output is not a valid PNG"


# ---------------------------------------------------------------------------
# Auth integration tests
# These run against the live stack. When API_KEYS="" (local dev default),
# all requests pass through — we verify no false 401s.
# ---------------------------------------------------------------------------

def test_list_jobs_empty_or_list():
    """GET /jobs returns a list (may be empty if no jobs exist)."""
    r = httpx.get(f"{BASE_URL}/jobs", timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_jobs_status_filter():
    """GET /jobs?status=COMPLETED returns only COMPLETED jobs (or empty list)."""
    # Submit a job so there's at least something in the table
    r = httpx.post(
        f"{BASE_URL}/jobs",
        json={"workflow_id": "txt2img-sdxl", "params": {"positive_prompt": "test", "checkpoint": "dummy.safetensors"}},
        timeout=10,
    )
    # 422 / 503 acceptable — we just need the list endpoint to filter correctly
    r = httpx.get(f"{BASE_URL}/jobs?status=COMPLETED", timeout=10)
    assert r.status_code == 200
    jobs = r.json()
    assert isinstance(jobs, list)
    for job in jobs:
        assert job["status"] == "COMPLETED"


def test_cancel_job_not_found():
    """DELETE /jobs/<unknown-id> returns 404."""
    r = httpx.delete(f"{BASE_URL}/jobs/00000000-0000-0000-0000-000000000000", timeout=10)
    assert r.status_code == 404


def test_cancel_job_transitions_to_cancelled():
    """Submit a job then immediately cancel it — status should be CANCELLED."""
    submit = httpx.post(
        f"{BASE_URL}/jobs",
        json={"workflow_id": "txt2img-sdxl", "params": {"positive_prompt": "cancel me", "checkpoint": "dummy.safetensors"}},
        timeout=10,
    )
    # May fail validation (404 workflow or 422) — skip if so
    if submit.status_code not in (202, 200):
        pytest.skip(f"Job submit returned {submit.status_code} — skipping cancel test")

    job_id = submit.json()["id"]
    cancel = httpx.delete(f"{BASE_URL}/jobs/{job_id}", timeout=10)
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"


def test_auth_health_always_accessible():
    """GET /health must return 200 regardless of auth config."""
    r = httpx.get(f"{BASE_URL}/health", timeout=10)
    assert r.status_code == 200


def test_auth_no_false_401_when_disabled():
    """/workflows should not 401 when API_KEYS is empty (local dev default)."""
    r = httpx.get(f"{BASE_URL}/workflows", timeout=10)
    # With API_KEYS="" auth is disabled — expect 200, never 401
    assert r.status_code != 401, "Got unexpected 401 — is API_KEYS set in the running stack?"


def test_auth_post_jobs_no_key_when_disabled():
    """POST /jobs without key should not 401 when auth is disabled."""
    r = httpx.post(
        f"{BASE_URL}/jobs",
        json={"workflow_id": "txt2img-sdxl", "params": {}},
        timeout=10,
    )
    # 422 = validation error (missing required param) — auth passed through
    # 404 = workflow not found — also fine, auth passed through
    # 401 = auth blocked it — fail
    assert r.status_code != 401, "Got unexpected 401 — auth should be disabled (API_KEYS='')"


# ---------------------------------------------------------------------------
# Model-sync integration tests
# Verify the model-sync init container logic: S3 → local disk via aws s3 sync.
# Requires LocalStack (docker compose up).
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _localstack_available(), reason="LocalStack not reachable — run docker compose up first")
def test_model_sync_script(tmp_path):
    """Model-sync init container correctly syncs S3 model files to local disk."""
    dummy_key = "models/checkpoints/test-sync-integration.safetensors"
    dummy_content = b"fake-safetensors-data-for-sync-integration-test"
    output_dir = tmp_path / "models"
    output_dir.mkdir()

    # Upload a dummy checkpoint to LocalStack S3 (mirrors what an operator would do)
    upload = subprocess.run(
        [
            "aws", "s3", "cp", "-",
            f"s3://{LOCALSTACK_BUCKET}/{dummy_key}",
            "--endpoint-url", LOCALSTACK_ENDPOINT,
        ],
        input=dummy_content,
        capture_output=True,
        env=_LOCALSTACK_ENV,
        timeout=15,
    )
    assert upload.returncode == 0, f"S3 upload failed: {upload.stderr.decode()}"

    # Run the same sync command as the model-sync init container entrypoint.sh
    sync = subprocess.run(
        [
            "aws", "s3", "sync",
            f"s3://{LOCALSTACK_BUCKET}/models/",
            str(output_dir),
            "--exact-timestamps",
            "--no-progress",
            "--endpoint-url", LOCALSTACK_ENDPOINT,
        ],
        capture_output=True,
        env=_LOCALSTACK_ENV,
        timeout=30,
    )
    assert sync.returncode == 0, f"Sync failed: {sync.stderr.decode()}"

    # Verify the model landed under the correct type subdirectory
    synced_file = output_dir / "checkpoints" / "test-sync-integration.safetensors"
    assert synced_file.exists(), f"Expected synced model not found at {synced_file}"
    assert synced_file.read_bytes() == dummy_content, "Synced file content does not match uploaded content"


@pytest.mark.skipif(not _localstack_available(), reason="LocalStack not reachable — run docker compose up first")
def test_model_sync_idempotent(tmp_path):
    """A second sync run with --exact-timestamps skips already-present files (no re-download)."""
    dummy_key = "models/loras/test-idempotent.safetensors"
    dummy_content = b"fake-lora-data"
    output_dir = tmp_path / "models"
    output_dir.mkdir()

    subprocess.run(
        ["aws", "s3", "cp", "-", f"s3://{LOCALSTACK_BUCKET}/{dummy_key}", "--endpoint-url", LOCALSTACK_ENDPOINT],
        input=dummy_content, capture_output=True, env=_LOCALSTACK_ENV, timeout=15, check=True,
    )

    # First sync — downloads the file
    subprocess.run(
        ["aws", "s3", "sync", f"s3://{LOCALSTACK_BUCKET}/models/", str(output_dir),
         "--exact-timestamps", "--no-progress", "--endpoint-url", LOCALSTACK_ENDPOINT],
        capture_output=True, env=_LOCALSTACK_ENV, timeout=30, check=True,
    )

    # Second sync — should be a no-op (nothing new to copy)
    sync2 = subprocess.run(
        ["aws", "s3", "sync", f"s3://{LOCALSTACK_BUCKET}/models/", str(output_dir),
         "--exact-timestamps", "--no-progress", "--endpoint-url", LOCALSTACK_ENDPOINT],
        capture_output=True, env=_LOCALSTACK_ENV, timeout=30,
    )
    assert sync2.returncode == 0
    # No-op sync produces no stdout lines starting with "download:"
    output_lines = [l for l in sync2.stdout.decode().splitlines() if l.startswith("download:")]
    assert output_lines == [], f"Expected no downloads on second sync, got: {output_lines}"
