"""Stable, machine-readable error codes.

These codes are part of the public API contract. Clients branch on them, so a code's
meaning must never change once released. Add new codes; never repurpose old ones.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Stable error identifiers returned in the API error envelope."""

    # --- Validation / request shape -------------------------------------
    VALIDATION_FAILED = "validation_failed"
    MALFORMED_REQUEST = "malformed_request"

    # --- Authentication --------------------------------------------------
    INVALID_CREDENTIALS = "invalid_credentials"
    TOKEN_EXPIRED = "token_expired"
    TOKEN_INVALID = "token_invalid"
    TOKEN_REUSED = "token_reused"
    NOT_AUTHENTICATED = "not_authenticated"
    EMAIL_NOT_VERIFIED = "email_not_verified"

    # --- Verification -----------------------------------------------------
    INVALID_CODE = "invalid_code"

    # --- Authorization ---------------------------------------------------
    FORBIDDEN = "forbidden"

    # --- Resources -------------------------------------------------------
    NOT_FOUND = "not_found"
    ALREADY_EXISTS = "already_exists"
    CONFLICT = "conflict"

    # --- Rate limiting ---------------------------------------------------
    RATE_LIMITED = "rate_limited"

    # --- Infrastructure --------------------------------------------------
    DATABASE_UNAVAILABLE = "database_unavailable"
    SERVICE_UNAVAILABLE = "service_unavailable"

    # --- Configuration ---------------------------------------------------
    CONFIGURATION_INVALID = "configuration_invalid"

    # --- Fallback --------------------------------------------------------
    INTERNAL_ERROR = "internal_error"
