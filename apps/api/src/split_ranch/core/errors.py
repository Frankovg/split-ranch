"""Application errors and RFC 9457 problem+json handlers."""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from split_ranch.domain import DomainError

PROBLEM_JSON = "application/problem+json"
PROBLEM_BASE = "https://split.ranch/problems/"

log = structlog.get_logger(__name__)


class AppError(Exception):
    """Base class for errors mapped to problem+json responses."""

    status: int = 400
    code: str = "bad_request"
    title: str = "Bad request"

    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str | None = None,
        status: int | None = None,
        extra: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(detail or self.title)
        self.detail = detail or self.title
        if code is not None:
            self.code = code
        if status is not None:
            self.status = status
        self.extra = extra or {}
        self.headers = headers or {}


class Unauthenticated(AppError):
    status = 401
    code = "unauthenticated"
    title = "Authentication required"


class TokenExpired(Unauthenticated):
    code = "token_expired"
    title = "Access token expired"


class Forbidden(AppError):
    status = 403
    code = "forbidden_role"
    title = "Not allowed"


class NotFound(AppError):
    status = 404
    code = "not_found"
    title = "Not found"


class Conflict(AppError):
    status = 409
    code = "conflict"
    title = "Conflict"


class PreconditionFailed(AppError):
    status = 412
    code = "version_conflict"
    title = "Version conflict"


class PreconditionRequired(AppError):
    status = 428
    code = "precondition_required"
    title = "If-Match header required"


class Unprocessable(AppError):
    status = 422
    code = "validation_error"
    title = "Unprocessable request"


class ServiceUnavailable(AppError):
    status = 503
    code = "service_unavailable"
    title = "Service unavailable"


def problem(
    status: int,
    code: str,
    title: str,
    detail: str | None = None,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body: dict[str, Any] = {
        "type": PROBLEM_BASE + code,
        "title": title,
        "status": status,
        "detail": detail or title,
        "code": code,
    }
    if extra:
        body.update(jsonable_encoder(extra))
    return JSONResponse(body, status_code=status, media_type=PROBLEM_JSON, headers=headers)


_STATUS_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden_role",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    412: "version_conflict",
    422: "validation_error",
    429: "rate_limited",
}


async def _app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, AppError)
    return problem(exc.status, exc.code, exc.title, exc.detail, exc.extra, exc.headers)


async def _domain_error_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, DomainError)
    return problem(422, exc.code, "Invalid split", exc.message)


async def _validation_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    errors = [
        {"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", "")}
        for e in exc.errors()
    ]
    return problem(
        422, "validation_error", "Validation error", "Request validation failed", {"errors": errors}
    )


async def _http_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, StarletteHTTPException)
    code = _STATUS_CODES.get(exc.status_code, "http_error")
    return problem(
        exc.status_code,
        code,
        str(exc.detail) if exc.detail else code,
        headers=dict(exc.headers or {}),
    )


async def _unhandled_handler(_: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_error", error=type(exc).__name__)
    return problem(500, "internal_error", "Internal server error")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error_handler)
    app.add_exception_handler(DomainError, _domain_error_handler)
    app.add_exception_handler(RequestValidationError, _validation_handler)
    app.add_exception_handler(StarletteHTTPException, _http_handler)
    app.add_exception_handler(Exception, _unhandled_handler)
