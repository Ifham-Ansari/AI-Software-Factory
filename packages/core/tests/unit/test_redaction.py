"""Secret redaction.

These are security tests. A failure here means credentials reach log aggregators.
"""

from __future__ import annotations

import json

import pytest

from factory_core.observability import REDACTED, SecretRedactor, get_logger, get_redactor

pytestmark = [pytest.mark.unit, pytest.mark.security]

SECRET = "supersecretpassword123"


@pytest.fixture
def redactor() -> SecretRedactor:
    return SecretRedactor()


class TestKnownValues:
    def test_registered_value_is_removed(self, redactor: SecretRedactor) -> None:
        redactor.register(SECRET)

        assert SECRET not in redactor.redact_text(f"connecting with {SECRET} now")

    def test_short_values_are_not_registered(self, redactor: SecretRedactor) -> None:
        """Redacting a 3-character secret would mangle unrelated text everywhere."""
        redactor.register("abc")

        assert redactor.redact_text("abc def") == "abc def"

    def test_clear_forgets_values(self, redactor: SecretRedactor) -> None:
        redactor.register(SECRET)
        redactor.clear()

        assert SECRET in redactor.redact_text(SECRET)


class TestSensitiveKeys:
    @pytest.mark.parametrize(
        "key",
        [
            "password",
            "Password",
            "api_key",
            "access_token",
            "authorization",
            "cookie",
            "jwt",
            "private_key",
            "db_password",
            "STRIPE_SECRET_KEY",
        ],
    )
    def test_value_redacted_by_key_name(self, redactor: SecretRedactor, key: str) -> None:
        assert redactor.redact({key: "anything at all"}) == {key: REDACTED}

    @pytest.mark.parametrize("key", ["token_type", "expires_in", "session_id", "token_id"])
    def test_allowlisted_keys_survive(self, redactor: SecretRedactor, key: str) -> None:
        """Over-redaction that removes useful debugging fields has its own cost."""
        assert redactor.redact({key: "bearer"}) == {key: "bearer"}

    @pytest.mark.parametrize("key", ["email", "user_id", "project_id", "name", "status"])
    def test_ordinary_keys_survive(self, redactor: SecretRedactor, key: str) -> None:
        assert redactor.redact({key: "value"}) == {key: "value"}


class TestPatterns:
    def test_jwt_redacted(self, redactor: SecretRedactor) -> None:
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abcdefghijklmnop"

        assert token not in redactor.redact_text(f"got {token}")

    def test_bearer_header_redacted(self, redactor: SecretRedactor) -> None:
        assert "abcdefghijklmnop" not in redactor.redact_text("Bearer abcdefghijklmnop")

    def test_url_password_redacted_username_kept(self, redactor: SecretRedactor) -> None:
        """The username is genuinely useful when debugging a connection failure."""
        cleaned = redactor.redact_text("postgresql://neon_owner:hunter2abc@ep.neon.tech/db")

        assert "hunter2abc" not in cleaned
        assert "neon_owner" in cleaned

    @pytest.mark.parametrize(
        "credential",
        [
            "sk-abcdefghijklmnopqrstuvwxyz",
            "ghp_abcdefghijklmnopqrstuvwxyz1234",
            "xoxb-1234567890-abcdefghijk",
        ],
    )
    def test_provider_key_shapes_redacted(self, redactor: SecretRedactor, credential: str) -> None:
        assert credential not in redactor.redact_text(f"key={credential}")

    def test_private_key_block_redacted(self, redactor: SecretRedactor) -> None:
        pem = "-----BEGIN RSA PRIVATE KEY-----\nMIIEabc\n-----END RSA PRIVATE KEY-----"

        assert "MIIEabc" not in redactor.redact_text(pem)


class TestNestedStructures:
    def test_recurses_into_nested_containers(self, redactor: SecretRedactor) -> None:
        redactor.register(SECRET)
        payload = {
            "user": {"email": "a@b.test", "password": "hunter2"},
            "connections": [{"dsn": f"postgres://u:{SECRET}@h/db"}],
            "tags": ("safe", SECRET),
        }

        cleaned = redactor.redact(payload)

        rendered = str(cleaned)
        assert SECRET not in rendered
        assert "hunter2" not in rendered
        assert "a@b.test" in rendered

    def test_non_string_scalars_pass_through(self, redactor: SecretRedactor) -> None:
        assert redactor.redact({"count": 5, "ok": True, "none": None}) == {
            "count": 5,
            "ok": True,
            "none": None,
        }


class TestLoggingIntegration:
    """The end-to-end guarantee: nothing secret reaches the log stream."""

    def test_planted_secret_never_appears_in_output(self, log_stream) -> None:  # type: ignore[no-untyped-def]
        get_redactor().register(SECRET)
        log = get_logger("test")

        log.info("db.connect", dsn=f"postgresql://user:{SECRET}@host/db")
        log.warning("auth.failed", password="hunter2", authorization="Bearer abcdefghijkl")

        output = log_stream.getvalue()

        assert SECRET not in output
        assert "hunter2" not in output
        assert "abcdefghijkl" not in output
        assert REDACTED in output

    def test_secret_in_traceback_is_redacted(self, log_stream) -> None:  # type: ignore[no-untyped-def]
        """Tracebacks are the leak path people forget about."""
        get_redactor().register(SECRET)
        log = get_logger("test")

        try:
            raise RuntimeError(f"could not connect to postgres://u:{SECRET}@h/db")
        except RuntimeError:
            log.exception("db.failed")

        assert SECRET not in log_stream.getvalue()

    def test_output_is_valid_json(self, log_stream) -> None:  # type: ignore[no-untyped-def]
        get_logger("test").info("event.happened", count=3)

        line = log_stream.getvalue().strip().splitlines()[-1]
        parsed = json.loads(line)

        assert parsed["event"] == "event.happened"
        assert parsed["count"] == 3
        assert parsed["level"] == "info"
