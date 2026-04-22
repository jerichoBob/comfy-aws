import asyncio
import base64
import logging
from datetime import datetime

from app.comfy_client import ComfyClient
from app.config import settings
from app.models.job import Job, JobStatus
from app.services import dynamo, s3
from app.services.metrics import record_job_error, timed_generation
from app.services.workflow import load_template, merge_params, validate_params

logger = logging.getLogger(__name__)

_comfy = ComfyClient()


async def _upload_image_params(job_id: str, schema, params: dict) -> dict:
    """For any param with type='image' whose value is a base64 data URI, upload to ComfyUI and replace with filename."""
    result = dict(params)
    for name, param in schema.params.items():
        if param.type != "image":
            continue
        value = result.get(name)
        if not isinstance(value, str) or not value.startswith("data:"):
            continue
        # Decode base64 data URI: "data:<mime>;base64,<data>"
        try:
            _, encoded = value.split(",", 1)
            image_data = base64.b64decode(encoded)
        except Exception as exc:
            raise ValueError(f"Invalid base64 image for param '{name}': {exc}") from exc
        filename = await _comfy.upload_image(f"{job_id}_{name}.png", image_data)
        result[name] = filename
        logger.info("Job %s: uploaded image param '%s' → %s", job_id, name, filename)
    return result


async def create_job(workflow_id: str, params: dict) -> Job:
    """Validate params, store job, submit to ComfyUI, launch background watch task."""
    graph, schema = load_template(workflow_id)
    validate_params(schema, params)

    job = Job(workflow_id=workflow_id, params=params)
    await dynamo.create_job(job)

    params = await _upload_image_params(job.id, schema, params)
    merged = merge_params(graph, schema, params)

    try:
        prompt_id = await _comfy.submit_prompt(merged)
    except Exception as exc:
        logger.error("Failed to submit job %s to ComfyUI: %s", job.id, exc)
        await dynamo.update_job(job.id, status=JobStatus.FAILED, error=str(exc))
        raise

    await dynamo.update_job(job.id, status=JobStatus.RUNNING, prompt_id=prompt_id)
    asyncio.create_task(_watch_job(job.id, prompt_id), name=f"watch-{job.id}")
    logger.info("Submitted job %s (prompt_id=%s)", job.id, prompt_id)

    job.status = JobStatus.RUNNING
    return job


async def _watch_job(job_id: str, prompt_id: str) -> None:
    """Background task: poll ComfyUI history, upload images, update DynamoDB."""
    output_keys: list[str] = []
    started_at = asyncio.get_event_loop().time()
    try:
        async with timed_generation(job_id):
            while True:
                await asyncio.sleep(2)
                history = await _comfy.get_history(prompt_id)
                if history is None:
                    continue

                status = history.get("status", {})
                if not status.get("completed"):
                    continue

                if status.get("status_str") == "error":
                    messages = status.get("messages", [])
                    error_msg = next(
                        (m[1].get("exception_message", "Unknown error")
                         for m in messages if m[0] == "execution_error"),
                        "ComfyUI execution error",
                    )
                    logger.error("Job %s execution error: %s", job_id, error_msg)
                    duration = round(asyncio.get_event_loop().time() - started_at, 2)
                    await dynamo.update_job(job_id, status=JobStatus.FAILED, error=error_msg, duration_seconds=duration)
                    return

                outputs = history.get("outputs", {})
                for node_output in outputs.values():
                    for img in node_output.get("images", []):
                        filename = img.get("filename", "")
                        subfolder = img.get("subfolder", "")
                        img_type = img.get("type", "output")
                        if not filename:
                            continue
                        try:
                            image_bytes = await _comfy.get_image(filename, subfolder, img_type)
                            key = await s3.upload_image(job_id, filename, image_bytes)
                            output_keys.append(key)
                            logger.info("Job %s: uploaded %s → %s", job_id, filename, key)
                        except Exception as exc:
                            logger.error("Job %s: failed to upload %s: %s", job_id, filename, exc)

                duration = round(asyncio.get_event_loop().time() - started_at, 2)
                await dynamo.update_job(job_id, status=JobStatus.COMPLETED, output_keys=output_keys, duration_seconds=duration)
                logger.info("Job %s completed in %.1fs with %d image(s)", job_id, duration, len(output_keys))
                return

    except Exception as exc:
        logger.error("Job %s watch failed: %s", job_id, exc)
        await dynamo.update_job(job_id, status=JobStatus.FAILED, error=str(exc))


async def list_jobs(status: str | None = None, limit: int = 20) -> list[Job]:
    return await dynamo.list_jobs(status=status, limit=limit)


async def get_job(job_id: str) -> Job | None:
    return await dynamo.get_job(job_id)


async def cancel_job(job_id: str) -> Job | None:
    job = await dynamo.get_job(job_id)
    if job is None:
        return None
    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        return job

    try:
        if job.status == JobStatus.RUNNING:
            # Interrupt the currently executing generation
            await _comfy.interrupt()
        else:
            # Remove from pending queue
            await _comfy.delete_from_queue(job_id)
    except Exception as exc:
        logger.warning("Could not cancel job %s in ComfyUI: %s", job_id, exc)

    await dynamo.update_job(job_id, status=JobStatus.CANCELLED)
    job.status = JobStatus.CANCELLED
    return job


async def recover_stale_jobs() -> None:
    """Mark RUNNING jobs older than JOB_TIMEOUT_SECONDS as FAILED."""
    stale = await dynamo.list_running_jobs_older_than(settings.job_timeout_seconds)
    for job in stale:
        logger.warning("Recovering stale job %s (timed out)", job.id)
        await dynamo.update_job(job.id, status=JobStatus.FAILED, error="Job timed out")
