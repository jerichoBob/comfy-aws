import logging

from fastapi import APIRouter, HTTPException

from app.comfy_client import ComfyClient

router = APIRouter()
logger = logging.getLogger(__name__)
_comfy = ComfyClient()


@router.get("/health")
async def health():
    try:
        stats = await _comfy.health_check()
        return {"status": "ok", "comfyui": stats}
    except Exception as exc:
        logger.error("Health check failed: %s", exc)
        raise HTTPException(status_code=503, detail=f"ComfyUI unreachable: {exc}")
