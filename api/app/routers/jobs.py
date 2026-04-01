import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app.models.job import Job
from app.services import cdn, job_service, s3

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRequest(BaseModel):
    workflow_id: str
    params: dict[str, Any]


async def _resolve_output_urls(job: Job) -> Job:
    """Populate job.output_urls from job.output_keys at response time.

    Uses CloudFront signed URLs when configured, falls back to S3 presigned URLs
    for local dev (LocalStack).
    """
    if not job.output_keys:
        return job

    urls = []
    for key in job.output_keys:
        try:
            if cdn.is_configured():
                # Calculate remaining TTL: URL should expire when the job DynamoDB record does
                from app.config import settings
                expires_in = settings.presigned_url_expiry_seconds  # default; CloudFront URLs can be longer
                url = cdn.generate_signed_url(key, expires_in_seconds=expires_in)
            else:
                url = await s3.generate_presigned_url(key)
            urls.append(url)
        except Exception as exc:
            logger.warning("Failed to generate URL for key %s: %s", key, exc)

    job.output_urls = urls
    return job


@router.get("", response_model=list[Job])
async def list_jobs(status: str | None = Query(default=None, description="Filter by job status (e.g. RUNNING, COMPLETED)")):
    jobs = await job_service.list_jobs(status=status)
    results = []
    for job in jobs:
        results.append(await _resolve_output_urls(job))
    return results


@router.post("", response_model=Job, status_code=202)
async def submit_job(req: JobRequest):
    try:
        job = await job_service.create_job(req.workflow_id, req.params)
        return await _resolve_output_urls(job)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc))


@router.get("/{job_id}", response_model=Job)
async def get_job(job_id: str):
    job = await job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return await _resolve_output_urls(job)


@router.delete("/{job_id}", response_model=Job)
async def cancel_job(job_id: str):
    job = await job_service.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return await _resolve_output_urls(job)
