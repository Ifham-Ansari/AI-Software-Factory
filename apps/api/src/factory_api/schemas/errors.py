"""The API error envelope.

Every failure — validation, authorization, missing resource, unexpected crash — returns
this shape. Clients branch on ``error.code``, never on the HTTP status alone and never on
message text, which is why codes are a stable enum.

``request_id`` is echoed so a user reporting a problem can quote one string that finds
every log line for that request.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from factory_core.errors import ErrorCode


class ErrorDetail(BaseModel):
    """A single field-level validation problem."""

    model_config = ConfigDict(extra="forbid")

    field: str = Field(description="Dotted path to the offending field.")
    message: str = Field(description="What is wrong with it.")


class ErrorBody(BaseModel):
    """The error itself."""

    model_config = ConfigDict(extra="forbid")

    code: ErrorCode = Field(description="Stable machine-readable error identifier.")
    message: str = Field(description="Human-readable description, safe to display.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Structured context. Never contains secrets."
    )
    fields: list[ErrorDetail] = Field(
        default_factory=list, description="Field-level problems, for validation failures."
    )
    request_id: str | None = Field(
        default=None, description="Correlates this response with server logs."
    )


class ErrorResponse(BaseModel):
    """Envelope returned for every non-2xx response."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "error": {
                    "code": "not_found",
                    "message": "The requested project was not found.",
                    "details": {},
                    "fields": [],
                    "request_id": "3f9a2c1b8e5d4a7f",
                }
            }
        },
    )

    error: ErrorBody
