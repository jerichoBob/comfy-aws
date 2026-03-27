import asyncio
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


async def create_job(workflow_id: str, params: dict) -> Job:
    """Validate params, store job, submit to ComfyUI, launch background watch task."""
    graph, schema = load_template(workflow_id)
    validate_params(schema, params)
    merged = merge_params(graph, schema, params)

    job = Job(workflow_id=workflow_id, params=params)
    await dynamo.create_job(job)

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


async def get_job(job_id: str) -> Job | None:
    return await dynamo.get_job(job_id)


async def cancel_job(job_id: str) -> Job | None:
    job = await dynamo.get_job(job_id)
    if job is None:
        return None
    if job.status not in (JobStatus.PENDING, JobStatus.RUNNING):
        return job

    try:
        # Best-effort: remove from ComfyUI queue (may have already started)
        await _comfy.delete_from_queue(job_id)
    except Exception as exc:
        logger.warning("Could not remove job %s from ComfyUI queue: %s", job_id, exc)

    await dynamo.update_job(job_id, status=JobStatus.CANCELLED)
    job.status = JobStatus.CANCELLED
    return job


async def recover_stale_jobs() -> None:
    """Mark RUNNING jobs older than JOB_TIMEOUT_SECONDS as FAILED."""
    stale = await dynamo.list_running_jobs_older_than(settings.job_timeout_seconds)
    for job in stale:
        logger.warning("Recovering stale job %s (timed out)", job.id)
        await dynamo.update_job(job.id, status=JobStatus.FAILED, error="Job timed out")
