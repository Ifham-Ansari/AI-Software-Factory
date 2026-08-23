"""How the service presents itself: HTTP surface and logging.

Separated from ``settings.py`` because these describe the *process* — where it listens,
who may call it, how loudly it logs — while that module holds the resources it depends on.
"""

from __future__ import annotations

import json
from typing import Annotated, Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


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

    # How long a single readiness probe may take. The default is generous on purpose:
    # against a serverless or geographically distant database, opening a fresh connection
    # (TLS handshake included) can take several seconds, and a readiness endpoint that
    # reports "down" for a working database is worse than no probe at all.
    health_timeout_seconds: float = Field(default=15.0, gt=0, le=60)

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
