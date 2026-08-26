"""Commands and views for the secret vault.

There is no schema here carrying a secret value *out*. :class:`SecretView` is what every
read path returns — name, description, timestamps, and whether a value is set. That is the
"write-only API" guarantee expressed as a type: an endpoint physically cannot return a
plaintext value, because no response model has a field to put one in.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

from factory_core.security.references import is_valid_secret_name

#: Long enough for a PEM key, short enough that a paste error is caught early.
MAX_SECRET_VALUE_LENGTH = 8_192


class StoreSecretCommand(BaseModel):
    """Store or replace one secret value."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=64)
    #: ``SecretStr`` so an accidental log or repr of this command shows nothing.
    value: SecretStr
    description: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        """Names are environment-variable shaped.

        They become environment variables at every sink, so anything else would either
        be silently mangled or become a shell-injection surface at the point of use.
        """
        if not is_valid_secret_name(value):
            msg = "Secret names must be uppercase letters, digits and underscores"
            raise ValueError(msg)
        return value

    @field_validator("value")
    @classmethod
    def _validate_value(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not raw:
            msg = "Secret value must not be empty"
            raise ValueError(msg)
        if len(raw) > MAX_SECRET_VALUE_LENGTH:
            msg = f"Secret value must be at most {MAX_SECRET_VALUE_LENGTH} characters"
            raise ValueError(msg)
        return value


class SecretView(BaseModel):
    """A secret's metadata. Never its value."""

    model_config = ConfigDict(extra="forbid")

    name: str
    description: str
    #: Always ``True`` for a row that exists. Present so a client can render the same
    #: component for a configured and an unconfigured requirement.
    is_set: bool = True
    version: int
    created_at: datetime
    updated_at: datetime
    last_accessed_at: datetime | None = None
    #: The `secret://` reference an agent would be handed. Safe to display.
    reference: str


class ResolutionRequest(BaseModel):
    """Context required to resolve a secret to its value.

    ``purpose`` is mandatory and free-text: the audit row is only useful if it says what
    the value was needed for, and a caller made to write it is a caller who has thought
    about whether it should be resolving at all.
    """

    model_config = ConfigDict(extra="forbid")

    purpose: str = Field(min_length=1, max_length=200)
    actor_type: str = Field(default="system", max_length=16)
    actor_id: str | None = Field(default=None, max_length=64)
    run_id: uuid.UUID | None = None
    request_id: str | None = Field(default=None, max_length=64)
