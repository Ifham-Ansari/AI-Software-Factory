"""Authentication commands and results.

Commands are validated Pydantic models rather than loose arguments, so an invalid email
or a too-short password is rejected at the service boundary regardless of which transport
called it.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from factory_core.domain.entities import User
from factory_core.domain.values import Email

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128


class RegisterCommand(BaseModel):
    """Create a new account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: Email
    password: SecretStr = Field(repr=False)
    display_name: str = Field(min_length=1, max_length=120)

    def password_value(self) -> str:
        """Read the plaintext password.

        An explicit call rather than an attribute, so every place the plaintext is read
        is greppable.
        """
        return self.password.get_secret_value()


class SignInCommand(BaseModel):
    """Authenticate an existing account."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    email: Email
    password: SecretStr = Field(repr=False)

    def password_value(self) -> str:
        """Read the plaintext password."""
        return self.password.get_secret_value()


class AuthSession(BaseModel):
    """A newly established or refreshed session.

    The tokens exist here only in transit to the caller. They are never persisted in this
    shape and never logged; ``repr=False`` keeps them out of tracebacks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    user: User
    access_token: str = Field(repr=False)
    refresh_token: str = Field(repr=False)
    access_expires_in: int
    refresh_expires_in: int
    token_type: str = "bearer"
