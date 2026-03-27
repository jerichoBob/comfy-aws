from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.models.job import Job
from app.services import job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


class JobRequest(BaseModel):
    workflow_id: str
    params: dict[str, Any]


@router.post("", response_model=Job, status_code=202)
async def submit_job(req: JobRequest):
    try:
        return await job_service.create_job(req.workflow_id, req.params)
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
    return job


@router.delete("/{job_id}", response_model=Job)
async def cancel_job(job_id: str):
    job = await job_service.cancel_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job
