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

from pydantic import AliasChoices, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Deliberately undeliverable: it is a marker meaning "nobody chose a sender yet". The
# ``.local`` TLD cannot resolve publicly, so an SMTP configuration still carrying this
# is refused rather than left to fail at send time against a real provider.
PLACEHOLDER_FROM_ADDRESS = "no-reply@ai-software-factory.local"


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
    ] = PLACEHOLDER_FROM_ADDRESS
    from_name: str = "AI Software Factory"

    smtp_host: str | None = None
    smtp_port: int = Field(default=587, ge=1, le=65535)
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_use_tls: bool = True
    smtp_timeout_seconds: float = Field(default=10.0, gt=0)

    @model_validator(mode="before")
    @classmethod
    def _trim_and_drop_blanks(cls, values: object) -> object:
        """Strip surrounding whitespace, then drop blanks so defaults apply.

        Both halves fix a real way an env file misconfigures this:

        * ``EMAIL__SMTP_HOST= smtp.gmail.com`` keeps the leading space, and a hostname
          with a space in it fails DNS resolution with an opaque ``gaierror`` at send
          time rather than anything that names the setting.
        * ``EMAIL__SMTP_HOST=`` is how a template ships an unset key, and how a
          deployment platform passes an empty variable. A blank must not beat the field
          default — otherwise the sender becomes ``From: <>``, which a real provider
          rejects just as opaquely.

        Only the ends are trimmed, so a Gmail App Password pasted in its displayed
        ``abcd efgh ijkl mnop`` form keeps its internal spacing.
        """
        if not isinstance(values, dict):
            return values
        trimmed = {
            key: value.strip() if isinstance(value, str) else value for key, value in values.items()
        }
        return {key: value for key, value in trimmed.items() if value != ""}

    @model_validator(mode="after")
    def _smtp_is_deliverable(self) -> EmailSettings:
        """Refuse an SMTP configuration that cannot actually send.

        Checked at startup rather than at send time: the first person to discover a
        misconfigured sender should not be a user who cannot finish signing up.
        """
        if self.transport != "smtp":
            return self
        problems: list[str] = []
        if not self.smtp_host:
            problems.append("EMAIL__SMTP_HOST is required when EMAIL__TRANSPORT is 'smtp'")
        if self.from_address == PLACEHOLDER_FROM_ADDRESS:
            problems.append(
                "EMAIL__FROM_ADDRESS must be set to a real address when "
                "EMAIL__TRANSPORT is 'smtp' (it is still the placeholder). With Gmail "
                "it must match EMAIL__SMTP_USERNAME"
            )
        elif "@" not in self.from_address:
            problems.append(
                f"EMAIL__FROM_ADDRESS must be a real address when EMAIL__TRANSPORT is "
                f"'smtp' (got {self.from_address!r})"
            )
        # Username without password (or vice versa) is always a mistake. Neither is fine:
        # a local relay such as Mailpit accepts unauthenticated mail.
        if bool(self.smtp_username) != bool(self.smtp_password):
            problems.append("EMAIL__SMTP_USERNAME and EMAIL__SMTP_PASSWORD must be set together")
        if problems:
            raise ValueError("; ".join(problems))
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
