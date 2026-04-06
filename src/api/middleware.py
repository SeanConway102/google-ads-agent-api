"""
API middleware — authentication, error handling, logging, request ID.
Applies to all routes in the Campaign Management API.
"""
import logging
import time
import uuid
from typing import Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from src.api.schemas import ErrorResponse
from src.config import get_admin_api_key

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────────────────
# Authentication middleware
# ──────────────────────────────────────────────────────────────────────────────

class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Validates the X-API-Key header against the configured ADMIN_API_KEY.
    Exempts health-check and docs routes.
    """

    EXEMPT_PATHS = {
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if any(request.url.path.startswith(p) for p in self.EXEMPT_PATHS):
            return await call_next(request)

        api_key = request.headers.get("x-api-key")
        expected_key = get_admin_api_key()

        if not api_key:
            return _json_error(
                "missing_api_key",
                "X-API-Key header is required",
                status=401,
                request=request,
            )

        if api_key != expected_key:
            logger.warning(f"Invalid API key attempt from {request.client}")
            return _json_error(
                "invalid_api_key",
                "The provided API key is invalid",
                status=401,
                request=request,
            )

        return await call_next(request)


# ──────────────────────────────────────────────────────────────────────────────
# Request logging middleware
# ──────────────────────────────────────────────────────────────────────────────

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    Logs all incoming requests with method, path, duration, and status code.
    Adds X-Request-ID header to all responses for tracing.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        request.state.request_id = request_id

        start_time = time.perf_counter()
        logger.info(
            "request_start",
            extra={
                "method": request.method,
                "path": request.url.path,
                "request_id": request_id,
                "client": str(request.client),
            }
        )

        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.exception(
                "request_error",
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "request_id": request_id,
                    "duration_ms": round(duration_ms, 2),
                    "error": str(exc),
                }
            )
            return _json_error(
                "internal_error",
                "An unexpected error occurred",
                status=500,
                request_id=request_id,
            )

        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            "request_end",
            extra={
                "method": request.method,
                "path": request.url.path,
                "request_id": request_id,
                "duration_ms": round(duration_ms, 2),
                "status_code": response.status_code,
            }
        )

        response.headers["X-Request-ID"] = request_id
        return response


# ──────────────────────────────────────────────────────────────────────────────
# Exception handlers
# ──────────────────────────────────────────────────────────────────────────────

async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
    """Handle Pydantic validation errors and other ValueError exceptions."""
    return _json_error("validation_error", str(exc), status=422, request=request)


async def key_error_handler(request: Request, exc: KeyError) -> JSONResponse:
    """Handle missing key errors in request data."""
    return _json_error("missing_field", f"Required field missing: {exc}", status=422, request=request)


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — logs and returns a generic error."""
    logger.exception(f"Unhandled exception: {exc}", exc_info=exc)
    return _json_error(
        "internal_error",
        "An unexpected error occurred",
        status=500,
        request=request,
    )


def setup_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers on the FastAPI app."""
    app.add_exception_handler(ValueError, value_error_handler)
    app.add_exception_handler(KeyError, key_error_handler)
    app.add_exception_handler(Exception, generic_exception_handler)

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _json_error(
    error_code: str,
    message: str,
    *,
    status: int,
    request: Request | None = None,
    request_id: str | None = None,
) -> JSONResponse:
    # Try to get request_id from: explicit arg > request.state > request headers
    rid = (
        request_id
        or (getattr(request.state, "request_id", None) if request else None)
        or (request.headers.get("x-request-id") if request else None)
    )
    body = ErrorResponse(
        error=error_code,
        detail=message,
        request_id=rid,
    )
    response = JSONResponse(content=body.model_dump(exclude_none=True), status_code=status)
    if rid:
        response.headers["X-Request-ID"] = rid
    return response


# ──────────────────────────────────────────────────────────────────────────────
# CORS middleware (optional, for browser-based clients)
# ──────────────────────────────────────────────────────────────────────────────

def setup_cors(app: FastAPI) -> None:
    """Configure CORS headers for browser-based API clients."""
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Restrict to specific origins in production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
