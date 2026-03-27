import logging
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from typing import Any

import aioboto3

from app.config import settings
from app.models.job import Job, JobStatus

logger = logging.getLogger(__name__)

_session = aioboto3.Session()


def _floats_to_decimal(obj: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB compatibility."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _floats_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_floats_to_decimal(v) for v in obj]
    return obj


def _client_kwargs() -> dict:
    kwargs: dict[str, Any] = {"region_name": settings.aws_default_region}
    if settings.aws_endpoint_url:
        kwargs["endpoint_url"] = settings.aws_endpoint_url
    return kwargs


def _job_to_item(job: Job) -> dict:
    expires_at = int(
        (datetime.now(timezone.utc) + timedelta(days=settings.job_ttl_days)).timestamp()
    )
    item: dict[str, Any] = {
        "PK": f"JOB#{job.id}",
        "id": job.id,
        "workflow_id": job.workflow_id,
        "params": _floats_to_decimal(job.params),
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "output_urls": job.output_urls,
        "expires_at": expires_at,
    }
    if job.error is not None:
        item["error"] = job.error
    return item


def _item_to_job(item: dict) -> Job:
    return Job(
        id=item["id"],
        workflow_id=item["workflow_id"],
        params=item.get("params", {}),
        status=JobStatus(item["status"]),
        created_at=datetime.fromisoformat(item["created_at"]),
        updated_at=datetime.fromisoformat(item["updated_at"]),
        output_urls=item.get("output_urls", []),
        error=item.get("error"),
    )


async def create_job(job: Job) -> None:
    async with _session.resource("dynamodb", **_client_kwargs()) as ddb:
        table = await ddb.Table(settings.dynamo_table)
        await table.put_item(Item=_job_to_item(job))
    logger.info("Created job %s", job.id)


async def get_job(job_id: str) -> Job | None:
    async with _session.resource("dynamodb", **_client_kwargs()) as ddb:
        table = await ddb.Table(settings.dynamo_table)
        response = await table.get_item(Key={"PK": f"JOB#{job_id}"})
    item = response.get("Item")
    if item is None:
        return None
    return _item_to_job(item)


async def update_job(job_id: str, **kwargs: Any) -> None:
    """Update arbitrary fields on a job item."""
    now = datetime.utcnow().isoformat()
    kwargs["updated_at"] = now

    # Convert enums to strings
    if "status" in kwargs and isinstance(kwargs["status"], JobStatus):
        kwargs["status"] = kwargs["status"].value

    expressions = []
    attr_names: dict[str, str] = {}
    attr_values: dict[str, Any] = {}

    for i, (key, value) in enumerate(kwargs.items()):
        placeholder = f"#f{i}"
        value_placeholder = f":v{i}"
        attr_names[placeholder] = key
        attr_values[value_placeholder] = value
        expressions.append(f"{placeholder} = {value_placeholder}")

    update_expr = "SET " + ", ".join(expressions)

    async with _session.resource("dynamodb", **_client_kwargs()) as ddb:
        table = await ddb.Table(settings.dynamo_table)
        await table.update_item(
            Key={"PK": f"JOB#{job_id}"},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=attr_names,
            ExpressionAttributeValues=attr_values,
        )
    logger.info("Updated job %s: %s", job_id, list(kwargs.keys()))


async def list_running_jobs_older_than(seconds: int) -> list[Job]:
    """Scan for RUNNING jobs older than `seconds` — used for timeout recovery."""
    cutoff = (
        datetime.utcnow() - timedelta(seconds=seconds)
    ).isoformat()

    async with _session.resource("dynamodb", **_client_kwargs()) as ddb:
        table = await ddb.Table(settings.dynamo_table)
        response = await table.query(
            IndexName="status-created_at-index",
            KeyConditionExpression="#s = :s AND #c < :cutoff",
            ExpressionAttributeNames={"#s": "status", "#c": "created_at"},
            ExpressionAttributeValues={":s": "RUNNING", ":cutoff": cutoff},
        )
    return [_item_to_job(item) for item in response.get("Items", [])]
