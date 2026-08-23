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

import json
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from factory_core.config.environment import Environment

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


class ObservabilitySettings(BaseSettings):
    """Logging and tracing."""

    model_config = SettingsConfigDict(
        env_prefix="OBSERVABILITY__", env_file=".env", extra="ignore", case_sensitive=False
    )

    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"
    service_name: str = "factory-api"
    otel_enabled: bool = False
    otel_endpoint: str | None = None


class ApiSettings(BaseSettings):
    """HTTP surface configuration."""

    model_config = SettingsConfigDict(
        env_prefix="API__", env_file=".env", extra="ignore", case_sensitive=False
    )

    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    root_path: str = ""
    # NoDecode suppresses Pydantic Settings' automatic JSON parsing of complex types.
    # Without it the raw env string is JSON-decoded before any validator runs, so a
    # plain comma-separated value raises a JSONDecodeError instead of reaching _split_csv.
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )
    docs_enabled: bool = True

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_csv(cls, value: Any) -> Any:
        """Accept a comma-separated string as well as a JSON list.

        Deployment platforms overwhelmingly supply plain strings for env vars.
        """
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("["):
                parsed = json.loads(text)
                return [str(origin).strip() for origin in parsed]
            return [origin.strip() for origin in text.split(",") if origin.strip()]
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
