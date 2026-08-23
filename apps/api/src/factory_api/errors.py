"""Exception handling.

Two rules:

1. **Nothing leaks.** An unexpected exception returns a generic 500 with a request id.
   The traceback goes to the logs, never to the client. A stack trace in a response body
   hands an attacker the framework versions, file paths, and often the SQL.
2. **Every failure has the same shape.** Clients parse one envelope regardless of which
   layer failed, so error handling on the client is written once.
"""

from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from factory_api.schemas.errors import ErrorBody, ErrorDetail, ErrorResponse
from factory_core.errors import AppError, ErrorCode
from factory_core.observability import get_logger, get_request_id

logger = get_logger(__name__)

# Starlette renamed this constant; the old spelling is deprecated but the numeric value is
# what actually matters. Bound once here so the rename is a one-line change.
_UNPROCESSABLE = 422

# Status codes that map to a stable code when Starlette raises them directly (a route
# that does not exist, a method that is not allowed).
_STATUS_CODES: dict[int, ErrorCode] = {
    status.HTTP_401_UNAUTHORIZED: ErrorCode.NOT_AUTHENTICATED,
    status.HTTP_403_FORBIDDEN: ErrorCode.FORBIDDEN,
    status.HTTP_404_NOT_FOUND: ErrorCode.NOT_FOUND,
    status.HTTP_409_CONFLICT: ErrorCode.CONFLICT,
    status.HTTP_429_TOO_MANY_REQUESTS: ErrorCode.RATE_LIMITED,
}


def _envelope(
    code: ErrorCode,
    message: str,
    status_code: int,
    *,
    details: dict[str, object] | None = None,
    fields: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Render an error envelope."""
    body = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            fields=fields or [],
            request_id=get_request_id(),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=body.model_dump(mode="json"),
        headers=headers,
    )


async def handle_app_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a typed application error."""
    error = exc if isinstance(exc, AppError) else AppError()
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if error.status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    logger.info(
        "request.failed",
        error_code=error.code.value,
        status_code=error.status_code,
        error_type=type(error).__name__,
    )
    return _envelope(
        error.code,
        error.message,
        error.status_code,
        details=error.details,
        headers=headers,
    )


async def handle_validation_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render a request-validation failure with per-field detail."""
    fields: list[ErrorDetail] = []
    if isinstance(exc, RequestValidationError):
        for item in exc.errors():
            # Drop the leading "body"/"query" segment: the client knows where it put the
            # value, and "body.email" is noisier than "email".
            path = [str(part) for part in item["loc"]]
            fields.append(ErrorDetail(field=".".join(path[1:] or path), message=item["msg"]))
    return _envelope(
        ErrorCode.VALIDATION_FAILED,
        "The request failed validation.",
        _UNPROCESSABLE,
        fields=fields,
    )


async def handle_http_exception(_request: Request, exc: Exception) -> JSONResponse:
    """Render an exception raised by the framework itself."""
    http_exc = exc if isinstance(exc, StarletteHTTPException) else None
    status_code = http_exc.status_code if http_exc else status.HTTP_500_INTERNAL_SERVER_ERROR
    detail = str(http_exc.detail) if http_exc and http_exc.detail else "Request failed."
    code = _STATUS_CODES.get(status_code, ErrorCode.INTERNAL_ERROR)
    headers = dict(http_exc.headers) if http_exc and http_exc.headers else None
    return _envelope(code, detail, status_code, headers=headers)


async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    """Render an unhandled exception without leaking anything about it.

    The full traceback is logged (and redacted on the way out); the client gets a code
    and a request id, which is everything they need to report the problem and nothing
    they could use to probe the system.
    """
    logger.exception("request.unhandled_error", error_type=type(exc).__name__)
    return _envelope(
        ErrorCode.INTERNAL_ERROR,
        "An unexpected error occurred.",
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Install every handler on the application."""
    app.add_exception_handler(AppError, handle_app_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, handle_http_exception)
    app.add_exception_handler(Exception, handle_unexpected_error)
