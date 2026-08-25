"""Production hardening and what configuration is safe to expose.

Split from ``test_config.py`` (loading and layering) because these are the security
properties: what production refuses to start with, what `/ready` may say out loud, and
what must never appear in a repr.
"""

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
from factory_core.observability.redaction import SecretRedactor

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


class TestIntegrationReport:
    """What `/ready` and the startup log say about optional dependencies."""

    def test_every_value_is_a_boolean(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Never the credentials themselves — this report is unauthenticated."""
        _set_valid(monkeypatch)

        report = load_settings().configured_integrations()

        assert report
        assert all(isinstance(value, bool) for value in report.values())

    def test_the_report_survives_redaction(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Regression: the vault's key was once called ``secrets``, and the redactor
        blanks any key containing "secret" — so the startup line reported ``[REDACTED]``
        and an operator could not tell whether the vault was configured."""
        _set_valid(monkeypatch)
        report = load_settings().configured_integrations()

        redacted = SecretRedactor().redact(report)

        assert redacted == report, f"a key name is tripping the redactor: {redacted}"


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
