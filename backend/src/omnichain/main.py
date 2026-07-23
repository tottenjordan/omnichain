"""FastAPI application factory for OmniChain."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, cast

from fastapi import FastAPI

from omnichain import __version__
from omnichain.api import gcs as gcs_router
from omnichain.errors import register_exception_handlers
from omnichain.logging_config import configure_logging, correlation_id_var

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, MutableMapping

    Scope = MutableMapping[str, object]
    Message = MutableMapping[str, object]
    Receive = Callable[[], Awaitable[Message]]
    Send = Callable[[Message], Awaitable[None]]
    ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

_HEADER = b"x-correlation-id"


class CorrelationIdMiddleware:
    """Pure-ASGI middleware that binds a correlation id to each request.

    Implemented at the ASGI layer (not BaseHTTPMiddleware) so the contextvar
    set here propagates to endpoints and to the error handlers that run as the
    stack unwinds. The id is not reset: each request runs in its own task
    context, so there is no cross-request leakage.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        raw_headers = cast("list[tuple[bytes, bytes]]", scope.get("headers") or [])
        raw = dict(raw_headers).get(_HEADER)
        cid = raw.decode() if raw else uuid.uuid4().hex
        correlation_id_var.set(cid)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(
                    cast("list[tuple[bytes, bytes]]", message.get("headers") or [])
                )
                response_headers.append((_HEADER, cid.encode()))
                message["headers"] = response_headers
            await send(message)

        await self.app(scope, receive, send_wrapper)


def create_app() -> FastAPI:
    """Build and configure the OmniChain FastAPI application."""
    configure_logging()
    app = FastAPI(title="OmniChain", version=__version__)
    app.add_middleware(CorrelationIdMiddleware)
    register_exception_handlers(app)

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(gcs_router.router)

    return app


app = create_app()
