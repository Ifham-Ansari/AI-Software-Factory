"""Authentication request and response bodies.

Tokens are returned in the response body rather than set as cookies by this service. The
web client is a Next.js BFF that immediately stores them in httpOnly cookies it controls
(see ``apps/web/src/app/api/auth``), which keeps tokens out of browser JavaScript while
leaving this API a plain, directly testable REST surface with no cookie policy baked in.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from factory_core.application.auth import AuthSession
from factory_core.domain.entities import User
from factory_core.domain.values import Email

MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_LENGTH = 128


class RegisterRequest(BaseModel):
    """Create an account."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "email": "ada@example.com",
                "password": "a-sufficiently-long-passphrase",
                "display_name": "Ada Lovelace",
            }
        },
    )

    email: Email = Field(description="Email address. Normalised to lowercase.")
    password: str = Field(
        min_length=MIN_PASSWORD_LENGTH,
        max_length=MAX_PASSWORD_LENGTH,
        description=(
            f"At least {MIN_PASSWORD_LENGTH} characters. Length is the requirement rather "
            "than character-class rules, which push users toward predictable substitutions."
        ),
    )
    display_name: str = Field(min_length=1, max_length=120)


class SignInRequest(BaseModel):
    """Authenticate an existing account."""

    model_config = ConfigDict(extra="forbid")

    email: Email
    # No length bounds beyond a sane maximum: rejecting a short password here would
    # reveal that the stored one is longer, and legacy passwords must still be able to
    # sign in and be rehashed.
    password: str = Field(min_length=1, max_length=MAX_PASSWORD_LENGTH)


class RefreshRequest(BaseModel):
    """Exchange a refresh token for a new session."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=512)


class SignOutRequest(BaseModel):
    """Revoke a session."""

    model_config = ConfigDict(extra="forbid")

    refresh_token: str = Field(min_length=1, max_length=512)


class VerifyEmailRequest(BaseModel):
    """Redeem a one-time verification code."""

    model_config = ConfigDict(extra="forbid")

    email: Email
    # Digits only, fixed length. Validated here so a malformed code never reaches the
    # comparison path and burns one of the caller's limited attempts.
    code: str = Field(min_length=6, max_length=10, pattern=r"^\d+$")


class ResendVerificationRequest(BaseModel):
    """Request a fresh verification code."""

    model_config = ConfigDict(extra="forbid")

    email: Email


class VerificationChallengeResponse(BaseModel):
    """Issued after registration or a resend.

    Carries no code and no identifier for one — only what the UI needs to render a timer
    and a resend button.
    """

    model_config = ConfigDict(extra="forbid")

    email: str
    expires_in: int = Field(description="Seconds until the code expires.")
    resend_available_in: int = Field(description="Seconds before another code may be requested.")
    message: str = "Check your email for a verification code."


class UserResponse(BaseModel):
    """A user, as returned to clients.

    Built from the domain entity, which structurally cannot carry a password hash.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    email: str
    display_name: str
    status: str
    created_at: datetime
    email_verified: bool

    @classmethod
    def from_entity(cls, user: User) -> UserResponse:
        """Project a domain user onto its wire representation."""
        return cls(
            id=str(user.id),
            email=user.email,
            display_name=user.display_name,
            status=user.status.value,
            created_at=user.created_at,
            # A boolean, not the timestamp: the client only needs to know whether to show
            # the verification prompt.
            email_verified=user.is_email_verified,
        )


class SessionResponse(BaseModel):
    """A newly established session."""

    model_config = ConfigDict(extra="forbid")

    user: UserResponse
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access-token lifetime in seconds.")
    refresh_expires_in: int = Field(description="Refresh-token lifetime in seconds.")

    @classmethod
    def from_session(cls, session: AuthSession) -> SessionResponse:
        """Project an application session onto its wire representation."""
        return cls(
            user=UserResponse.from_entity(session.user),
            access_token=session.access_token,
            refresh_token=session.refresh_token,
            token_type=session.token_type,
            expires_in=session.access_expires_in,
            refresh_expires_in=session.refresh_expires_in,
        )
