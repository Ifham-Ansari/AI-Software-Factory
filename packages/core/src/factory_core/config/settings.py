"""Application settings.

Two rules govern this module:

1. **Secrets are typed ``SecretStr``.** They never render in logs, reprs, or tracebacks
   by accident. Reading one requires an explicit ``.get_secret_value()`` call, which is
   greppable and reviewable.
2. **Public configuration is explicitly marked.** ``Settings.public_config()`` returns
   only values that are safe to expose. Nothing reaches a client unless it is listed
   there, so adding a secret field cannot accidentally leak it.

Nested settings are populated with a double-underscore delimiter, e.g.
``DATABASE__POOL_SIZE=10``. Flat aliases exist for the handful of variables that
conventionally have well-known names (``DATABASE_URL``, ``JWT_SECRET_KEY``).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from factory_core.config.email import EmailSettings, VerificationSettings
from factory_core.config.environment import Environment
from factory_core.config.integrations import (
    LangSmithSettings,
    OpenAISettings,
    RedisSettings,
)
from factory_core.config.service import ApiSettings, ObservabilitySettings

_MIN_SECRET_LENGTH = 32


class DatabaseSettings(BaseSettings):
    """Postgres connection and pooling.

    psycopg 3 is the only driver in this system; see architecture.md §15.
    """

    model_config = SettingsConfigDict(
        env_prefix="DATABASE__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        # A field carrying a validation_alias is otherwise unreachable by its Python
        # name, which breaks direct construction in tests and embedding code.
        populate_by_name=True,
    )

    url: Annotated[
        SecretStr,
        Field(validation_alias=AliasChoices("DATABASE__URL", "DATABASE_URL")),
    ]
    pool_size: int = Field(default=5, ge=1, le=50)
    max_overflow: int = Field(default=5, ge=0, le=50)
    pool_timeout_seconds: float = Field(default=10.0, gt=0)
    pool_recycle_seconds: int = Field(default=1800, gt=0)
    command_timeout_seconds: float = Field(default=30.0, gt=0)
    echo: bool = False

    @field_validator("url")
    @classmethod
    def _require_psycopg_driver(cls, value: SecretStr) -> SecretStr:
        """Normalise and enforce the psycopg 3 async driver.

        A bare ``postgresql://`` URL would select SQLAlchemy's default sync driver and
        fail confusingly at connect time. Rewriting it here means operators can paste a
        Neon connection string unmodified.
        """
        raw = value.get_secret_value()
        if not raw.strip():
            msg = "DATABASE_URL must not be empty"
            raise ValueError(msg)
        if raw.startswith("postgresql+psycopg://"):
            return value
        if raw.startswith(("postgresql://", "postgres://")):
            _, _, remainder = raw.partition("://")
            return SecretStr(f"postgresql+psycopg://{remainder}")
        msg = "DATABASE_URL must be a postgresql:// or postgresql+psycopg:// URL"
        raise ValueError(msg)


class SecuritySettings(BaseSettings):
    """Token signing and password hashing parameters."""

    model_config = SettingsConfigDict(
        env_prefix="SECURITY__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    jwt_secret_key: Annotated[
        SecretStr,
        Field(validation_alias=AliasChoices("SECURITY__JWT_SECRET_KEY", "JWT_SECRET_KEY")),
    ]
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    jwt_issuer: str = "ai-software-factory"
    jwt_audience: str = "ai-software-factory-api"

    access_token_ttl_seconds: int = Field(default=600, ge=60, le=3600)
    refresh_token_ttl_seconds: int = Field(default=2_592_000, ge=3600)

    # Argon2id parameters. Defaults follow OWASP's second recommended configuration
    # (19 MiB, t=2, p=1), which resists GPU attack while staying fast enough for an
    # interactive login.
    argon2_time_cost: int = Field(default=2, ge=1, le=10)
    argon2_memory_cost_kib: int = Field(default=19_456, ge=8192)
    argon2_parallelism: int = Field(default=1, ge=1, le=16)

    @field_validator("jwt_secret_key")
    @classmethod
    def _reject_weak_secret(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) < _MIN_SECRET_LENGTH:
            msg = f"JWT_SECRET_KEY must be at least {_MIN_SECRET_LENGTH} characters"
            raise ValueError(msg)
        return value


class Settings(BaseSettings):
    """Root settings object. Construct via ``factory_core.config.get_settings()``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Environment = Environment.DEVELOPMENT
    database: DatabaseSettings
    security: SecuritySettings
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    api: ApiSettings = Field(default_factory=ApiSettings)

    # Optional, and consumed by later phases. Present now so credentials have a redacted
    # home before the code that uses them exists. See config/integrations.py.
    email: EmailSettings = Field(default_factory=EmailSettings)
    verification: VerificationSettings = Field(default_factory=VerificationSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    openai: OpenAISettings = Field(default_factory=OpenAISettings)
    langsmith: LangSmithSettings = Field(default_factory=LangSmithSettings)

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Settings:
        """Refuse to start production with development conveniences enabled.

        These are the settings most likely to be left on by accident, and each one is a
        real exposure in production.
        """
        if not self.environment.is_production:
            return self
        problems: list[str] = []
        if self.api.docs_enabled:
            problems.append("API__DOCS_ENABLED must be false in production")
        if "*" in self.api.cors_origins:
            problems.append("API__CORS_ORIGINS must not contain '*' in production")
        if self.observability.log_format != "json":
            problems.append("OBSERVABILITY__LOG_FORMAT must be 'json' in production")
        if self.database.echo:
            problems.append("DATABASE__ECHO must be false in production")
        if self.email.transport == "console":
            # The console transport writes the message body to the log, and the body
            # contains a one-time code. That is a credential in a log aggregator.
            problems.append(
                "EMAIL__TRANSPORT must be 'smtp' in production; 'console' logs one-time codes"
            )
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def public_config(self) -> dict[str, Any]:
        """Configuration safe to expose outside the process.

        This is an allowlist. A field is public only if it appears here.
        """
        return {
            "environment": self.environment.value,
            "service_name": self.observability.service_name,
            "docs_enabled": self.api.docs_enabled,
        }

    def configured_integrations(self) -> dict[str, bool]:
        """Which optional external services have credentials.

        Booleans only — never the credentials themselves. Safe to log at startup and to
        surface on the readiness endpoint, which is unauthenticated.
        """
        return {
            "email": self.email.is_configured,
            "redis": self.redis.is_configured,
            "openai": self.openai.is_configured,
            "langsmith": self.langsmith.is_configured,
        }

    def secret_values(self) -> list[str]:
        """Every secret this process holds, for registration with the redactor.

        Central so that adding a credential to configuration automatically protects it.
        A secret that is configured but never registered here is one that can reach a log.
        """
        values: list[str] = [
            self.database.url.get_secret_value(),
            self.security.jwt_secret_key.get_secret_value(),
        ]
        for optional in (
            self.redis.url,
            self.openai.api_key,
            self.langsmith.api_key,
            self.email.smtp_password,
        ):
            if optional is not None:
                values.append(optional.get_secret_value())
        return values
