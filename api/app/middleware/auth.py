import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings

logger = logging.getLogger(__name__)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Auth disabled when no keys configured
        if not settings.api_key_set:
            return await call_next(request)

        # Health endpoint is always exempt
        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)

        key = request.headers.get("X-API-Key", "")
        if not key or key not in settings.api_key_set:
            return JSONResponse(
                {"detail": "Invalid or missing API key"}, status_code=401
            )

        logger.info("auth key_prefix=%s", key[:8])
        return await call_next(request)
