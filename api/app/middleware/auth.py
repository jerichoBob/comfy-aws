import logging

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.config import settings

logger = logging.getLogger(__name__)


class ApiKeyMiddleware(BaseHTTPMiddleware):
    def _extract_key(self, request: Request) -> str | None:
        auth_header = request.headers.get("authorization", "")
        if auth_header:
            scheme, _, value = auth_header.partition(" ")
            if scheme.lower() == "bearer":
                return value.strip() or None
            # Non-Bearer Authorization scheme with no X-API-Key fallback → reject
            x_key = request.headers.get("x-api-key", "")
            return x_key or None
        return request.headers.get("x-api-key") or None

    async def dispatch(self, request: Request, call_next):
        if not settings.api_key_set:
            return await call_next(request)

        if request.url.path == "/health" and request.method == "GET":
            return await call_next(request)

        auth_header = request.headers.get("authorization", "")
        if auth_header:
            scheme = auth_header.partition(" ")[0]
            if scheme.lower() != "bearer" and not request.headers.get("x-api-key"):
                return JSONResponse(
                    {"detail": "Invalid or missing API key"}, status_code=401
                )

        key = self._extract_key(request)
        if not key or key not in settings.api_key_set:
            return JSONResponse(
                {"detail": "Invalid or missing API key"}, status_code=401
            )

        logger.info("auth key_prefix=%s", key[:8])
        return await call_next(request)
