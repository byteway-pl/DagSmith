"""Consistent API error shape: ``{code, message, detail}``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


class DagSmithError(Exception):
    """Base class for API errors carrying the response payload."""

    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


class NotFoundError(DagSmithError):
    status_code = 404
    code = "not_found"


class ConflictError(DagSmithError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(DagSmithError):
    status_code = 422
    code = "validation_failed"


class ForbiddenError(DagSmithError):
    status_code = 403
    code = "forbidden"


class UnauthorizedError(DagSmithError):
    status_code = 401
    code = "unauthorized"


class BadRequestError(DagSmithError):
    status_code = 400
    code = "bad_request"


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DagSmithError)
    async def _dagsmith_error_handler(_request: Request, exc: DagSmithError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message, "detail": exc.detail},
        )
