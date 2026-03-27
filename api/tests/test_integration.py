"""Integration tests — require docker compose up (ComfyUI + LocalStack)."""
import os

import httpx
import pytest

BASE_URL = os.environ.get("API_URL", "http://localhost:8000")
COMFYUI_URL = os.environ.get("COMFYUI_URL", "http://localhost:8188")


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
