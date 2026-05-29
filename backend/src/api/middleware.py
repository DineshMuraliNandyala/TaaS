"""
FastAPI middleware — rate limiting and structured error responses.
Uses slowapi (Starlette-native limiter backed by in-memory storage).
"""
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from backend.src.config import settings
from backend.src.logger import get_logger

log = get_logger(__name__)

# Module-level limiter — imported into routes that need per-endpoint limits
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{settings.rate_limit_per_minute}/minute"],
)


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Returns a structured JSON error instead of the default plain text."""
    log.warning(
        "rate_limit_exceeded",
        client_ip=get_remote_address(request),
        path=request.url.path,
        limit=str(exc.detail),
    )
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Too many requests. Limit: {exc.detail}",
            "retry_after_seconds": 60,
        },
    )


async def log_requests_middleware(request: Request, call_next) -> Response:
    """
    Logs every incoming request with method, path, status, and duration.
    Skips health check endpoint to avoid log noise.
    """
    import time
    if request.url.path == "/health":
        return await call_next(request)

    start = time.time()
    response = await call_next(request)
    duration_ms = int((time.time() - start) * 1000)

    log.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration_ms,
        client=request.client.host if request.client else "unknown",
    )
    return response