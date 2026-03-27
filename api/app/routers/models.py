import logging

from fastapi import APIRouter, HTTPException

from app.comfy_client import ComfyClient

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger(__name__)
_comfy = ComfyClient()


@router.get("")
async def get_models():
    """List available models from ComfyUI (checkpoints, loras, vaes).

    S3 key structure for models:
      models/checkpoints/
      models/loras/
      models/vaes/
    """
    try:
        return await _comfy.get_models()
    except Exception as exc:
        logger.error("Failed to fetch models: %s", exc)
        raise HTTPException(status_code=503, detail=f"ComfyUI unreachable: {exc}")
