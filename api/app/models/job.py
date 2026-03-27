from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
import uuid


class JobStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Job(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_id: str
    params: dict[str, Any]
    status: JobStatus = JobStatus.PENDING
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    # Stored in DynamoDB as S3 keys (e.g. "outputs/{job_id}/image.png")
    output_keys: list[str] = Field(default_factory=list)
    # Populated at response time (CloudFront signed URLs or S3 presigned URLs)
    output_urls: list[str] = Field(default_factory=list)
    error: str | None = None
    duration_seconds: float | None = None
