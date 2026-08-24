"""Email configuration: whitespace, blanks, and SMTP deliverability guards.

Split from ``test_config.py`` (which owns loading, layering and fail-fast) because these
are one subject with enough cases to stand alone.

Every case here is reachable by copying ``.env.example`` and flipping the transport, and
each one would otherwise surface as an opaque provider rejection — a DNS ``gaierror``, or
a bounced ``From: <>`` — to the first person who tried to register.
"""

from __future__ import annotations

import pytest

from factory_core.config import load_settings
from factory_core.config.email import PLACEHOLDER_FROM_ADDRESS
from factory_core.config.settings import (
    ApiSettings,
    DatabaseSettings,
    EmailSettings,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_core.errors import ConfigurationError

pytestmark = pytest.mark.unit

VALID_SECRET = "k" * 40
VALID_DB_URL = "postgresql://user:pw@localhost:5432/factory"

_EMAIL_FIELDS = (
    "TRANSPORT",
    "FROM_ADDRESS",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Detach settings from any ``.env`` on disk.

    A developer's own ``.env`` is on the settings search path. Without this a test that
    omits a variable would silently inherit their value and stop testing what it claims
    to — passing locally and failing in CI, or vice versa.
    """
    for model in (
        Settings,
        DatabaseSettings,
        SecuritySettings,
        ObservabilitySettings,
        ApiSettings,
        EmailSettings,
    ):
        monkeypatch.setitem(model.model_config, "env_file", "nonexistent.env")


def _email_env(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    """Set the whole EMAIL__ block, blanking anything not named.

    Blanking is equivalent to unset: blanks fall back to field defaults.
    """
    monkeypatch.setenv("DATABASE_URL", VALID_DB_URL)
    monkeypatch.setenv("JWT_SECRET_KEY", VALID_SECRET)
    for field in _EMAIL_FIELDS:
        monkeypatch.setenv(f"EMAIL__{field}", overrides.get(field, ""))


class TestBlanksAndWhitespace:
    def test_blank_values_fall_back_to_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A template ships keys with empty values; a blank must not beat the default."""
        _email_env(monkeypatch)

        email = load_settings().email

        assert email.transport == "console"
        assert email.from_address == PLACEHOLDER_FROM_ADDRESS
        assert email.smtp_host is None

    def test_surrounding_whitespace_is_trimmed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """`EMAIL__SMTP_HOST= smtp.gmail.com` must not become a hostname with a space."""
        _email_env(
            monkeypatch,
            TRANSPORT="smtp",
            SMTP_HOST=" smtp.gmail.com",
            FROM_ADDRESS="  someone@gmail.com ",
            SMTP_USERNAME=" someone@gmail.com ",
            SMTP_PASSWORD=" sixteencharacters ",
        )

        email = load_settings().email

        assert email.smtp_host == "smtp.gmail.com"
        assert email.from_address == "someone@gmail.com"
        assert email.smtp_username == "someone@gmail.com"

    def test_an_app_password_keeps_its_internal_spacing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Google displays App Passwords as four space-separated groups."""
        _email_env(
            monkeypatch,
            TRANSPORT="smtp",
            SMTP_HOST="smtp.gmail.com",
            FROM_ADDRESS="someone@gmail.com",
            SMTP_USERNAME="someone@gmail.com",
            SMTP_PASSWORD=" abcd efgh ijkl mnop ",
        )

        password = load_settings().email.smtp_password

        assert password is not None
        assert password.get_secret_value() == "abcd efgh ijkl mnop"


class TestSmtpDeliverability:
    def test_smtp_without_a_host_is_refused(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _email_env(monkeypatch, TRANSPORT="smtp", FROM_ADDRESS="someone@gmail.com")

        with pytest.raises(ConfigurationError, match="EMAIL__SMTP_HOST"):
            load_settings()

    def test_smtp_still_on_the_placeholder_sender_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`.local` resolves nowhere, so a real provider would reject every send."""
        _email_env(monkeypatch, TRANSPORT="smtp", SMTP_HOST="smtp.gmail.com")

        with pytest.raises(ConfigurationError, match="EMAIL__FROM_ADDRESS"):
            load_settings()

    def test_a_sender_that_is_not_an_address_is_refused(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _email_env(
            monkeypatch,
            TRANSPORT="smtp",
            SMTP_HOST="smtp.gmail.com",
            FROM_ADDRESS="not-an-address",
        )

        with pytest.raises(ConfigurationError, match="EMAIL__FROM_ADDRESS"):
            load_settings()

    @pytest.mark.parametrize(
        ("username", "password"),
        [("someone@gmail.com", ""), ("", "an-app-password")],
    )
    def test_half_configured_credentials_are_refused(
        self, monkeypatch: pytest.MonkeyPatch, username: str, password: str
    ) -> None:
        _email_env(
            monkeypatch,
            TRANSPORT="smtp",
            SMTP_HOST="smtp.gmail.com",
            FROM_ADDRESS="someone@gmail.com",
            SMTP_USERNAME=username,
            SMTP_PASSWORD=password,
        )

        with pytest.raises(ConfigurationError, match="together"):
            load_settings()

    def test_a_complete_gmail_configuration_loads(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _email_env(
            monkeypatch,
            TRANSPORT="smtp",
            SMTP_HOST="smtp.gmail.com",
            FROM_ADDRESS="someone@gmail.com",
            SMTP_USERNAME="someone@gmail.com",
            SMTP_PASSWORD="sixteencharacters",
        )

        assert load_settings().email.is_configured

    def test_an_unauthenticated_local_relay_is_allowed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Mailpit and friends accept mail with no credentials; that is not a mistake."""
        _email_env(
            monkeypatch,
            TRANSPORT="smtp",
            SMTP_HOST="127.0.0.1",
            SMTP_PORT="1025",
            FROM_ADDRESS="dev@example.com",
        )

        assert load_settings().email.is_configured
