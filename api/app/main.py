import asyncio
import logging
import logging.config

from fastapi import FastAPI

from app.logging_config import get_logging_config
from app.middleware.auth import ApiKeyMiddleware
from app.routers import health, jobs, models, workflows
from app.services.job_service import recover_stale_jobs

logging.config.dictConfig(get_logging_config())
logger = logging.getLogger(__name__)

app = FastAPI(title="comfy-aws", description="FastAPI wrapper around ComfyUI")

app.add_middleware(ApiKeyMiddleware)

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(models.router)
app.include_router(workflows.router)


@app.on_event("startup")
async def startup():
    logger.info("comfy-aws starting up")
    # Start background stale-job recovery loop
    asyncio.create_task(_recovery_loop(), name="recovery-loop")


async def _recovery_loop():
    while True:
        try:
            await recover_stale_jobs()
        except Exception as exc:
            logger.warning("Recovery loop error: %s", exc)
        await asyncio.sleep(60)
