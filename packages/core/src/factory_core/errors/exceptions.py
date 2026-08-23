"""Typed application exceptions.

Every failure that crosses a module boundary is one of these. The API layer maps them
to HTTP responses; nothing else needs to know about HTTP.

Rules:
    * Never raise a bare ``Exception``.
    * Never swallow a failure to keep a flow alive.
    * ``message`` is safe to show a caller. Anything sensitive goes in structured logs,
      never in the message or ``details``.
"""

from __future__ import annotations

from typing import Any

from factory_core.errors.codes import ErrorCode


class AppError(Exception):
    """Base class for every expected application failure.

    Attributes:
        code: Stable machine-readable identifier for the failure.
        message: Human-readable, caller-safe description.
        status_code: HTTP status the API layer should use.
        details: Optional structured context. Must never contain secrets.
    """

    code: ErrorCode = ErrorCode.INTERNAL_ERROR
    status_code: int = 500
    message: str = "An unexpected error occurred."

    def __init__(
        self,
        message: str | None = None,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or type(self).message
        self.details = details or {}
        super().__init__(self.message)

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code.value!r}, message={self.message!r})"


# --- Validation ----------------------------------------------------------


class ValidationError(AppError):
    """Request or command failed validation."""

    code = ErrorCode.VALIDATION_FAILED
    status_code = 422
    message = "The request failed validation."


# --- Authentication ------------------------------------------------------


class AuthenticationError(AppError):
    """Caller is not authenticated, or authentication material is unusable."""

    code = ErrorCode.NOT_AUTHENTICATED
    status_code = 401
    message = "Authentication is required."


class InvalidCredentialsError(AuthenticationError):
    """Email or password did not match.

    The message is deliberately identical for unknown-email and wrong-password so the
    endpoint cannot be used to enumerate registered accounts.
    """

    code = ErrorCode.INVALID_CREDENTIALS
    message = "Invalid email or password."


class TokenExpiredError(AuthenticationError):
    """Token was well-formed but past its expiry."""

    code = ErrorCode.TOKEN_EXPIRED
    message = "The token has expired."


class TokenInvalidError(AuthenticationError):
    """Token was malformed, tampered with, or of the wrong type."""

    code = ErrorCode.TOKEN_INVALID
    message = "The token is invalid."


class TokenReusedError(AuthenticationError):
    """A refresh token was presented twice.

    Treated as theft: the whole token family is revoked.
    """

    code = ErrorCode.TOKEN_REUSED
    message = "The session has been revoked. Please sign in again."


# --- Authorization -------------------------------------------------------


class AuthorizationError(AppError):
    """Caller is authenticated but not permitted to perform this action."""

    code = ErrorCode.FORBIDDEN
    status_code = 403
    message = "You do not have permission to perform this action."


# --- Resources -----------------------------------------------------------


class NotFoundError(AppError):
    """Requested resource does not exist, or is not visible to this caller.

    Used for both cases on purpose: returning 404 rather than 403 for a resource owned
    by someone else prevents callers from discovering that it exists.
    """

    code = ErrorCode.NOT_FOUND
    status_code = 404
    message = "The requested resource was not found."


class AlreadyExistsError(AppError):
    """A uniqueness constraint would be violated."""

    code = ErrorCode.ALREADY_EXISTS
    status_code = 409
    message = "The resource already exists."


class ConflictError(AppError):
    """The request conflicts with the current state of the resource."""

    code = ErrorCode.CONFLICT
    status_code = 409
    message = "The request conflicts with the current state."


# --- Infrastructure ------------------------------------------------------


class DatabaseUnavailableError(AppError):
    """The database could not be reached."""

    code = ErrorCode.DATABASE_UNAVAILABLE
    status_code = 503
    message = "The service is temporarily unavailable."


class ServiceUnavailableError(AppError):
    """A required dependency is unavailable."""

    code = ErrorCode.SERVICE_UNAVAILABLE
    status_code = 503
    message = "The service is temporarily unavailable."


# --- Configuration -------------------------------------------------------


class ConfigurationError(AppError):
    """Configuration is missing or invalid.

    Raised at startup so the process fails fast rather than serving traffic in a
    half-configured state.
    """

    code = ErrorCode.CONFIGURATION_INVALID
    status_code = 500
    message = "The application is misconfigured."
