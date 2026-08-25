"""Configuration loading, layering, and fail-fast behaviour."""

from __future__ import annotations

import pytest

from factory_core.config import Environment, load_settings
from factory_core.config.settings import (
    ApiSettings,
    DatabaseSettings,
    EmailSettings,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
    VerificationSettings,
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
    # A developer who configures real mail locally must not flip the result of the
    # production-hardening tests, which assert on the *default* transport.
    "EMAIL__TRANSPORT",
    "EMAIL__FROM_ADDRESS",
    "EMAIL__SMTP_HOST",
    "EMAIL__SMTP_USERNAME",
    "EMAIL__SMTP_PASSWORD",
)

_SETTINGS_MODELS = (
    Settings,
    DatabaseSettings,
    SecuritySettings,
    ObservabilitySettings,
    ApiSettings,
    EmailSettings,
    VerificationSettings,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test from a known-empty environment.

    Settings read a ``.env`` file by default. Pointing that at a nonexistent path stops a
    developer's local ``.env`` from silently satisfying a "missing variable" test — which
    would make the suite pass on their machine and fail in CI. ``setitem`` restores the
    original value afterwards, so class state does not leak between tests.

    Every settings model needs detaching, not just the required ones: the root conftest
    also loads ``.env`` into ``os.environ``, so a section left attached picks up local
    values through both routes.
    """
    for name in _MANAGED_VARS:
        monkeypatch.delenv(name, raising=False)
    for model in _SETTINGS_MODELS:
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
