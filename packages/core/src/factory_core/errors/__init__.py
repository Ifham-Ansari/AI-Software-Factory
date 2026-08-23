"""Typed error taxonomy shared by every layer."""

from factory_core.errors.codes import ErrorCode
from factory_core.errors.exceptions import (
    AlreadyExistsError,
    AppError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    ConflictError,
    DatabaseUnavailableError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    NotFoundError,
    ServiceUnavailableError,
    TokenExpiredError,
    TokenInvalidError,
    TokenReusedError,
    ValidationError,
)

__all__ = [
    "AlreadyExistsError",
    "AppError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "ConflictError",
    "DatabaseUnavailableError",
    "EmailNotVerifiedError",
    "ErrorCode",
    "InvalidCredentialsError",
    "NotFoundError",
    "ServiceUnavailableError",
    "TokenExpiredError",
    "TokenInvalidError",
    "TokenReusedError",
    "ValidationError",
]
