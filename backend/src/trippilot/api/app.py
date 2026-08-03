"""FastAPI application entry point."""

# pyright: reportUnusedFunction=false
# FastAPI registers the local exception handlers through decorators.

from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .middleware import (
    DEFAULT_MAX_REQUEST_BYTES,
    DEFAULT_REQUEST_TIMEOUT_SECONDS,
    RequestLimitsMiddleware,
)
from .routes import router
from .schemas import InternalErrorResponse, RequestErrorDetail, RequestErrorResponse


def _validate_cors_origins(origins: tuple[str, ...]) -> tuple[str, ...]:
    for origin in origins:
        parsed = urlsplit(origin)
        if (
            origin == "*"
            or parsed.scheme != "http"
            or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
            or parsed.username
            or parsed.password
        ):
            raise ValueError("CORS must list explicit local HTTP origins")
    return origins


def _cors_origins_from_environment() -> tuple[str, ...]:
    configured = os.getenv("TRIPPILOT_CORS_ORIGINS", "")
    origins = tuple(
        origin.strip() for origin in configured.split(",") if origin.strip()
    )
    return _validate_cors_origins(origins)


def create_app(
    *,
    max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
    request_timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    cors_origins: tuple[str, ...] | None = None,
) -> FastAPI:
    application = FastAPI(
        title="TripPilot API",
        summary="Offline delivery layer for proposed deterministic itineraries.",
        description=(
            "Plans one-to-four-day, single-destination proposed trips using "
            "versioned mock data. Nothing is booked or reserved."
        ),
        version="0.1.0",
        debug=False,
    )
    application.add_middleware(
        RequestLimitsMiddleware,
        max_request_bytes=max_request_bytes,
        timeout_seconds=request_timeout_seconds,
    )
    allowed_origins = (
        _cors_origins_from_environment() if cors_origins is None else cors_origins
    )
    allowed_origins = _validate_cors_origins(allowed_origins)
    if allowed_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(allowed_origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Content-Type"],
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(
        _request: Request, error: RequestValidationError
    ) -> JSONResponse:
        response = RequestErrorResponse(
            status="error",
            error_code="REQUEST_VALIDATION_ERROR",
            explanation="The request body did not satisfy the API contract.",
            details=tuple(
                RequestErrorDetail(
                    location=tuple(part for part in item["loc"] if part != "body"),
                    message=item["msg"],
                )
                for item in error.errors()
            ),
        )
        return JSONResponse(status_code=422, content=response.model_dump(mode="json"))

    @application.exception_handler(Exception)
    async def unexpected_error(_request: Request, _error: Exception) -> JSONResponse:
        response = InternalErrorResponse(
            status="error",
            error_code="INTERNAL_ERROR",
            explanation="The request could not be completed due to an internal error.",
        )
        return JSONResponse(status_code=500, content=response.model_dump(mode="json"))

    application.include_router(router)
    return application


app = create_app()
