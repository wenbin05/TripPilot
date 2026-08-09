"""Small local HTTP resource limits required by the security boundary."""

from __future__ import annotations

import asyncio
import time
from collections import deque

from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .schemas import InternalErrorResponse, RequestErrorDetail, RequestErrorResponse

DEFAULT_MAX_REQUEST_BYTES = 32_768
DEFAULT_REQUEST_TIMEOUT_SECONDS = 10.0


class RequestLimitsMiddleware:
    """Bound request bodies and total request handling time."""

    def __init__(
        self,
        app: ASGIApp,
        max_request_bytes: int = DEFAULT_MAX_REQUEST_BYTES,
        timeout_seconds: float = DEFAULT_REQUEST_TIMEOUT_SECONDS,
    ) -> None:
        self.app = app
        self.max_request_bytes = max_request_bytes
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False
        state = scope.setdefault("state", {})
        state["trippilot_request_deadline_monotonic"] = (
            time.monotonic() + self.timeout_seconds
        )

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            async with asyncio.timeout(self.timeout_seconds):
                messages: deque[Message] = deque()
                body_bytes = 0
                while True:
                    message = await receive()
                    messages.append(message)
                    if message["type"] != "http.request":
                        break
                    body_bytes += len(message.get("body", b""))
                    if body_bytes > self.max_request_bytes:
                        await self._request_too_large(scope, receive, send)
                        return
                    if not message.get("more_body", False):
                        break

                async def replay_receive() -> Message:
                    if messages:
                        return messages.popleft()
                    return {"type": "http.disconnect"}

                await self.app(scope, replay_receive, tracked_send)
        except TimeoutError:
            if response_started:
                raise
            await self._timed_out(scope, receive, send)

    @staticmethod
    async def _request_too_large(scope: Scope, receive: Receive, send: Send) -> None:
        response = RequestErrorResponse(
            status="error",
            error_code="REQUEST_VALIDATION_ERROR",
            explanation="The request body did not satisfy the API contract.",
            details=(
                RequestErrorDetail(
                    location=("body",),
                    message="Request body exceeds the configured size limit.",
                ),
            ),
        )
        await JSONResponse(status_code=422, content=response.model_dump(mode="json"))(
            scope, receive, send
        )

    @staticmethod
    async def _timed_out(scope: Scope, receive: Receive, send: Send) -> None:
        response = InternalErrorResponse(
            status="error",
            error_code="INTERNAL_ERROR",
            explanation="The request could not be completed due to an internal error.",
        )
        await JSONResponse(status_code=500, content=response.model_dump(mode="json"))(
            scope, receive, send
        )
