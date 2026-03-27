import logging
from typing import Any

import aioboto3

from app.config import settings

logger = logging.getLogger(__name__)

_session = aioboto3.Session()


def _client_kwargs() -> dict:
    kwargs: dict[str, Any] = {"region_name": settings.aws_default_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


async def upload_image(job_id: str, filename: str, data: bytes) -> str:
    """Upload image bytes to S3 and return a presigned URL.

    S3 key: outputs/{job_id}/{filename}
    """
    key = f"outputs/{job_id}/{filename}"
    async with _session.client("s3", **_client_kwargs()) as s3:
        await s3.put_object(
            Bucket=settings.s3_bucket,
            Key=key,
            Body=data,
            ContentType="image/png",
        )

    # Generate presigned URL — optionally using a different endpoint (local dev)
    presigned_kwargs = _client_kwargs()
    if settings.presigned_url_endpoint:
        presigned_kwargs["endpoint_url"] = settings.presigned_url_endpoint
    async with _session.client("s3", **presigned_kwargs) as s3:
        presigned_url = await s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=settings.presigned_url_expiry_seconds,
        )
    logger.info("Uploaded %s for job %s → %s", filename, job_id, key)
    return presigned_url
