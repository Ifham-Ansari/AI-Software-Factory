"""Configuration loading, layering, and fail-fast behaviour."""

from __future__ import annotations

import pytest

from factory_core.config import Environment, load_settings
from factory_core.config.settings import (
    ApiSettings,
    DatabaseSettings,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_core.errors import ConfigurationError

pytestmark = pytest.mark.unit

VALID_SECRET = "k" * 40
VALID_DB_URL = "postgresql://user:pw@localhost:5432/factory"

_MANAGED_VARS = (
    "DATABASE_URL",
    "DATABASE__URL",
    "DATABASE__POOL_SIZE",
    "DATABASE__ECHO",
    "JWT_SECRET_KEY",
    "SECURITY__JWT_SECRET_KEY",
    "SECURITY__ACCESS_TOKEN_TTL_SECONDS",
    "API__CORS_ORIGINS",
    "API__DOCS_ENABLED",
    "OBSERVABILITY__LOG_FORMAT",
    "ENVIRONMENT",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a known-empty environment.

    Settings read a ``.env`` file by default. Pointing that at a nonexistent path stops a
    developer's local ``.env`` from silently satisfying a "missing variable" test — which
    would make the suite pass on their machine and fail in CI. ``setitem`` restores the
    original value afterwards, so class state does not leak between tests.
    """
    for name in _MANAGED_VARS:
        monkeypatch.delenv(name, raising=False)
    for model in (Settings, DatabaseSettings, SecuritySettings, ObservabilitySettings, ApiSettings):
        monkeypatch.setitem(model.model_config, "env_file", "nonexistent.env")


def _set_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", VALID_DB_URL)
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)


class TestFailFast:
    def test_missing_variables_are_named(self) -> None:
        with pytest.raises(ConfigurationError) as exc_info:
            load_settings()

        message = exc_info.value.message
        assert "DATABASE_URL is required" in message
        assert "JWT_SECRET_KEY is required" in message

    def test_all_problems_reported_at_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One restart per missing variable would be a miserable first-run experience."""
        monkeypatch.setenv("DATABASE_URL", VALID_DB_URL)

        with pytest.raises(ConfigurationError) as exc_info:
            load_settings()

        assert "JWT_SECRET_KEY is required" in exc_info.value.message

    def test_weak_jwt_secret_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", VALID_DB_URL)
        monkeypatch.setenv("JWT_SECRET_KEY", "too-short")

        with pytest.raises(ConfigurationError, match="at least 32 characters"):
            load_settings()

    def test_empty_database_url_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "   ")
        monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)

        with pytest.raises(ConfigurationError):
            load_settings()

    def test_non_postgres_url_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DATABASE_URL", "mysql://user:pw@localhost/db")
        monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)

        with pytest.raises(ConfigurationError, match="postgresql"):
            load_settings()


class TestDriverNormalisation:
    @pytest.mark.parametrize(
        "given",
        ["postgresql://u:p@h/db", "postgres://u:p@h/db", "postgresql+psycopg://u:p@h/db"],
    )
    def test_rewrites_to_psycopg_async_driver(
        self, monkeypatch: pytest.MonkeyPatch, given: str
    ) -> None:
        """A pasted Neon connection string must work without hand-editing."""
        monkeypatch.setenv("DATABASE_URL", given)
        monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)

        url = load_settings().database.url.get_secret_value()

        assert url.startswith("postgresql+psycopg://")


class TestLayering:
    def test_prefixed_variables_override_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_valid(monkeypatch)
        monkeypatch.setenv("DATABASE__POOL_SIZE", "17")

        assert load_settings().database.pool_size == 17

    def test_cors_origins_accepts_csv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_valid(monkeypatch)
        monkeypatch.setenv("API__CORS_ORIGINS", "http://a.test, http://b.test")

        assert load_settings().api.cors_origins == ["http://a.test", "http://b.test"]

    def test_cors_origins_accepts_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_valid(monkeypatch)
        monkeypatch.setenv("API__CORS_ORIGINS", '["http://a.test"]')

        assert load_settings().api.cors_origins == ["http://a.test"]

    def test_defaults_apply_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_valid(monkeypatch)
        settings = load_settings()

        assert settings.environment is Environment.DEVELOPMENT
        assert settings.security.access_token_ttl_seconds == 600


class TestProductionHardening:
    @pytest.mark.parametrize(
        ("variable", "value", "expected"),
        [
            ("API__DOCS_ENABLED", "true", "DOCS_ENABLED"),
            ("API__CORS_ORIGINS", "*", "CORS_ORIGINS"),
            ("OBSERVABILITY__LOG_FORMAT", "console", "LOG_FORMAT"),
            ("DATABASE__ECHO", "true", "ECHO"),
        ],
    )
    def test_development_conveniences_refused(
        self,
        monkeypatch: pytest.MonkeyPatch,
        variable: str,
        value: str,
        expected: str,
    ) -> None:
        _set_valid(monkeypatch)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("API__DOCS_ENABLED", "false")
        monkeypatch.setenv(variable, value)

        with pytest.raises(ConfigurationError, match=expected):
            load_settings()

    def test_hardened_production_config_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_valid(monkeypatch)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("API__DOCS_ENABLED", "false")
        # The console email transport prints one-time codes to the log, so production
        # also requires a real transport — host and a deliverable sender both.
        monkeypatch.setenv("EMAIL__TRANSPORT", "smtp")
        monkeypatch.setenv("EMAIL__SMTP_HOST", "smtp.example.com")
        monkeypatch.setenv("EMAIL__FROM_ADDRESS", "no-reply@example.com")

        settings = load_settings()

        assert settings.environment.is_production
        assert not settings.api.docs_enabled
        assert settings.email.transport == "smtp"
        assert settings.email.is_configured

    def test_console_email_transport_refused_in_production(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The console transport logs a one-time verification code."""
        _set_valid(monkeypatch)
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("API__DOCS_ENABLED", "false")

        with pytest.raises(ConfigurationError, match="EMAIL__TRANSPORT"):
            load_settings()


class TestSecretExposure:
    def test_secrets_absent_from_repr(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _set_valid(monkeypatch)
        settings = load_settings()

        rendered = f"{settings!r} {settings.database.url!s} {settings.security!r}"

        assert "pw@localhost" not in rendered
        assert VALID_SECRET not in rendered

    def test_public_config_is_an_allowlist(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Adding a secret field must never widen what is publicly exposed."""
        _set_valid(monkeypatch)

        public = load_settings().public_config()

        assert set(public) == {"environment", "service_name", "docs_enabled"}
        assert VALID_SECRET not in str(public)


class TestEnvironment:
    def test_production_flags(self) -> None:
        assert Environment.PRODUCTION.is_production
        assert Environment.PRODUCTION.is_deployed
        assert not Environment.PRODUCTION.allows_debug_detail

    def test_development_flags(self) -> None:
        assert not Environment.DEVELOPMENT.is_production
        assert not Environment.DEVELOPMENT.is_deployed
        assert Environment.DEVELOPMENT.allows_debug_detail
