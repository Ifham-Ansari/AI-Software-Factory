"""Configuration for external services consumed by later phases.

These settings exist in Phase 1 even though nothing reads them yet, and that is
deliberate. Credentials need a correct home *before* the code that uses them is written:
a `SecretStr` field is registered with the redactor at startup, so the value can never
reach a log line, a trace, or an error body — whereas a raw `os.environ` lookup added
hastily in Phase 3 has no such protection.

Every section here is **optional**. Leaving them unset changes nothing about how the
platform behaves today; it simply reports the dependency as unconfigured.

| Section | Consumed by | Phase |
|---|---|---|
| Redis | events, rate limiting, idempotency, distributed locks | 2 |
| OpenAI | agent inference | 3 |
| LangSmith | tracing and evaluation | 3 |
"""

from __future__ import annotations

from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class RedisSettings(BaseSettings):
    """Redis connection (Phase 2).

    Upstash issues a ``rediss://`` URL. Both ``REDIS_URL`` and ``REDIS_API_KEY`` are
    accepted for the same value — the latter because that is what Upstash's console
    labels it, and rejecting a name the provider itself uses would be needless friction.
    """

    model_config = SettingsConfigDict(
        env_prefix="REDIS__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    url: Annotated[
        SecretStr | None,
        Field(validation_alias=AliasChoices("REDIS__URL", "REDIS_URL", "REDIS_API_KEY")),
    ] = None

    max_connections: int = Field(default=10, ge=1, le=100)
    socket_timeout_seconds: float = Field(default=5.0, gt=0)

    @field_validator("url", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        """Treat an empty variable as absent.

        A template copied to ``.env`` leaves ``REDIS_URL=`` behind. That should mean "not
        configured", not "configured with an empty URL" — which would fail at connect time
        with a far less obvious error.
        """
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("url")
    @classmethod
    def _require_redis_scheme(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        raw = value.get_secret_value()
        if not raw.startswith(("redis://", "rediss://")):
            msg = "REDIS_URL must start with redis:// or rediss://"
            raise ValueError(msg)
        return value

    @property
    def is_configured(self) -> bool:
        """Whether a Redis URL was supplied."""
        return self.url is not None


class OpenAISettings(BaseSettings):
    """OpenAI credentials (Phase 3).

    No model name lives here on purpose. Model choice is a per-agent-role decision made by
    the ``ModelRegistry`` in Phase 3, because the right model for routing is not the right
    model for code generation. A single ``OPENAI_MODEL`` variable would flatten that.
    """

    model_config = SettingsConfigDict(
        env_prefix="OPENAI__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    api_key: Annotated[
        SecretStr | None,
        Field(validation_alias=AliasChoices("OPENAI__API_KEY", "OPENAI_API_KEY")),
    ] = None

    base_url: str | None = None
    timeout_seconds: float = Field(default=60.0, gt=0)
    max_retries: int = Field(default=3, ge=0, le=10)

    @field_validator("api_key", "base_url", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_configured(self) -> bool:
        """Whether an API key was supplied."""
        return self.api_key is not None


class LangSmithSettings(BaseSettings):
    """LangSmith tracing and evaluation (Phase 3).

    ``LANGSMITH_API_KEY`` is the current name and ``LANGCHAIN_API_KEY`` the legacy alias;
    both are accepted because the SDK itself still honours the old one and half the
    documentation on the internet uses it.

    Tracing is off unless explicitly enabled. It ships payloads to a third party, which is
    a decision that should be made deliberately rather than inherited from a stray
    environment variable — and Phase 3 installs redaction hooks before it is switched on.
    """

    model_config = SettingsConfigDict(
        env_prefix="LANGSMITH__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    api_key: Annotated[
        SecretStr | None,
        Field(
            validation_alias=AliasChoices(
                "LANGSMITH__API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"
            )
        ),
    ] = None

    tracing: Annotated[
        bool,
        Field(
            validation_alias=AliasChoices(
                "LANGSMITH__TRACING", "LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"
            )
        ),
    ] = False

    project: Annotated[
        str,
        Field(validation_alias=AliasChoices("LANGSMITH__PROJECT", "LANGSMITH_PROJECT")),
    ] = "ai-software-factory"

    endpoint: str = "https://api.smith.langchain.com"

    @field_validator("api_key", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def is_configured(self) -> bool:
        """Whether tracing is both enabled and has a key to authenticate with."""
        return self.tracing and self.api_key is not None
