import logging
import time
from contextlib import asynccontextmanager
from typing import AsyncIterator

import aioboto3

from app.config import settings

logger = logging.getLogger(__name__)

_session = aioboto3.Session()
NAMESPACE = "ComfyAws"


def _client_kwargs() -> dict:
    kwargs = {"region_name": settings.aws_default_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


async def _put_metric(metric_name: str, value: float, unit: str = "None") -> None:
    try:
        async with _session.client("cloudwatch", **_client_kwargs()) as cw:
            await cw.put_metric_data(
                Namespace=NAMESPACE,
                MetricData=[
                    {
                        "MetricName": metric_name,
                        "Value": value,
                        "Unit": unit,
                    }
                ],
            )
    except Exception as exc:
        logger.warning("Failed to publish metric %s: %s", metric_name, exc)


async def record_generation_duration(seconds: float) -> None:
    """Publish GenerationDuration metric in seconds."""
    await _put_metric("GenerationDuration", seconds, "Seconds")


async def record_job_error() -> None:
    """Increment JobErrors count."""
    await _put_metric("JobErrors", 1.0, "Count")


async def record_queue_depth(depth: int) -> None:
    """Publish QueueDepth gauge."""
    await _put_metric("QueueDepth", float(depth), "Count")


@asynccontextmanager
async def timed_generation(job_id: str) -> AsyncIterator[None]:
    """Context manager that records generation duration + errors."""
    start = time.monotonic()
    try:
        yield
        elapsed = time.monotonic() - start
        await record_generation_duration(elapsed)
    except Exception:
        await record_job_error()
        raise
