"""Typed application errors and FastAPI exception handlers.

All failures surface to the client as a structured ``{"error": {...}}`` body.
OmniChain never falls back to another video model; generation failures are
raised as :class:`GenerationError` and shown to the user as-is.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi.responses import JSONResponse

from omnichain.logging_config import correlation_id_var

if TYPE_CHECKING:
    from fastapi import FastAPI, Request

logger = logging.getLogger("omnichain.errors")


class OmniChainError(Exception):
    """Base class for expected, client-surfaceable errors."""

    status_code: int = 500
    error_type: str = "omnichain_error"

    def __init__(
        self,
        message: str,
        *,
        detail: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        if status_code is not None:
            self.status_code = status_code


class GenerationError(OmniChainError):
    """Raised when Omni Flash / the Interactions API fails. No fallback."""

    status_code = 502
    error_type = "generation_error"


class GcsError(OmniChainError):
    """Raised when a Cloud Storage operation fails."""

    status_code = 502
    error_type = "gcs_error"


class AgentError(OmniChainError):
    """Raised when an ADK agent fails or returns unparseable output."""

    status_code = 502
    error_type = "agent_error"


class NotFoundError(OmniChainError):
    """Raised when a requested resource does not exist."""

    status_code = 404
    error_type = "not_found"


class AssemblyError(OmniChainError):
    """Raised when FFmpeg concat/mux fails."""

    status_code = 502
    error_type = "assembly_error"


def _error_body(error_type: str, message: str, detail: str | None) -> dict[str, object]:
    return {
        "error": {
            "type": error_type,
            "message": message,
            "detail": detail,
            "correlation_id": correlation_id_var.get(),
        }
    }


async def _omnichain_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, OmniChainError)  # noqa: S101 - handler is registered for this type
    logger.warning("omnichain_error", extra={"error_type": exc.error_type, "detail": exc.detail})
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.error_type, exc.message, exc.detail),
    )


async def _unhandled_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content=_error_body("internal_error", "Internal server error", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register OmniChain + catch-all exception handlers on the app."""
    app.add_exception_handler(OmniChainError, _omnichain_error_handler)
    app.add_exception_handler(Exception, _unhandled_error_handler)
