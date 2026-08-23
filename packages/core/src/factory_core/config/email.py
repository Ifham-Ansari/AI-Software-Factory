"""Email delivery and verification-code policy.

Two separate concerns that happen to live together: how mail leaves the process, and the
rules governing the one-time codes it carries.

The code policy numbers are security parameters, not preferences. A six-digit code has
only a million possibilities, so what actually protects it is the *attempt limit* and the
*expiry*, not the code itself. Both are configurable, and the defaults are deliberately
tight: 6 attempts, 10 minutes.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EmailSettings(BaseSettings):
    """How verification mail is delivered.

    ``transport`` chooses the sender:

    * ``console`` writes the message to the log. Development only — the process refuses
      to start in production with this set, because it would mean printing one-time codes
      into a log aggregator.
    * ``smtp`` sends real mail and requires a host.
    """

    model_config = SettingsConfigDict(
        env_prefix="EMAIL__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    transport: Literal["console", "smtp"] = "console"

    from_address: Annotated[
        str,
        Field(validation_alias=AliasChoices("EMAIL__FROM_ADDRESS", "EMAIL_FROM")),
    ] = "no-reply@ai-software-factory.local"
    from_name: str = "AI Software Factory"

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = Field(default=10.0, gt=0)

    @field_validator("smtp_host", "smtp_username", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("smtp_password", mode="before")
    @classmethod
    def _blank_password_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @model_validator(mode="after")
    def _smtp_needs_a_host(self) -> EmailSettings:
        if self.transport == "smtp" and not self.smtp_host:
            msg = "EMAIL__SMTP_HOST is required when EMAIL__TRANSPORT is 'smtp'"
            raise ValueError(msg)
        return self

    @property
    def is_configured(self) -> bool:
        """Whether real mail can be sent."""
        return self.transport == "smtp" and self.smtp_host is not None


class VerificationSettings(BaseSettings):
    """One-time email verification codes.

    A six-digit code is worth ~20 bits. Brute-forcing it online is what the attempt limit
    prevents; the short expiry bounds how long a leaked code stays useful. Raising
    ``code_length`` is the lever if that trade needs changing.
    """

    model_config = SettingsConfigDict(
        env_prefix="VERIFICATION__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    code_length: int = Field(default=6, ge=6, le=10)
    ttl_seconds: int = Field(default=600, ge=60, le=3600)

    # Wrong guesses before the code is destroyed. Low on purpose: with 10^6 codes and a
    # 10-minute window, 6 attempts leaves a ~1-in-166,000 chance per issued code.
    max_attempts: int = Field(default=6, ge=1, le=20)

    # Minimum gap between sends, so the endpoint cannot be used to flood an inbox.
    resend_cooldown_seconds: int = Field(default=60, ge=0, le=3600)

    # Codes issued per address per day, whether or not they are used.
    max_per_day: int = Field(default=10, ge=1, le=100)

    @property
    def ttl_minutes(self) -> int:
        """Expiry in whole minutes, for display in the email and the UI."""
        return max(1, self.ttl_seconds // 60)
