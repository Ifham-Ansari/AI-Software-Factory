"""High-entropy credential detection [F-205].

The entropy filter is the redactor's only heuristic strategy, so it needs tests in both
directions. A false negative leaks a credential; a false positive redacts the correlation
id out of every log line and makes an incident untraceable. The second failure mode is
easy to introduce and hard to notice, which is why the "must survive" cases below outnumber
the "must redact" ones.
"""

from __future__ import annotations

import pytest

from factory_core.observability.entropy import looks_like_credential, shannon_entropy
from factory_core.observability.redaction import REDACTED, SecretRedactor

pytestmark = pytest.mark.unit


class TestEntropyScoring:
    def test_random_scores_higher_than_prose(self) -> None:
        random_like = "Zx9Kq2Lm8Pv4Nw7Rt3Yb6Hs1Jd5Fg0Ac"
        prose = "the deployment completed successfully"

        assert shannon_entropy(random_like) > shannon_entropy(prose)

    def test_empty_string_scores_zero(self) -> None:
        assert shannon_entropy("") == 0.0

    def test_single_repeated_character_scores_zero(self) -> None:
        """No information content, so it must never trip the filter."""
        assert shannon_entropy("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa") == 0.0
        assert not looks_like_credential("aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa")


@pytest.mark.security
class TestCredentialsAreRedacted:
    @pytest.mark.parametrize(
        ("label", "text"),
        [
            ("unknown provider key", "token=Zx9Kq2Lm8Pv4Nw7Rt3Yb6Hs1Jd5Fg0Ac"),
            ("base64 blob", "dGhpcyBpcyBhIHZlcnkgbG9uZyBzZWNyZXQgdmFsdWUxMjM0NQ=="),
            ("mixed alnum secret", "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF"),
        ],
    )
    def test_high_entropy_tokens_are_redacted(self, label: str, text: str) -> None:
        """These match no known pattern and are not registered values. Entropy is the
        only thing that catches them."""
        assert REDACTED in SecretRedactor().redact_text(text)

    def test_a_secret_inside_a_sentence_is_redacted(self) -> None:
        text = "provider rejected key aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF for account 42"

        result = SecretRedactor().redact_text(text)

        assert "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF" not in result
        assert "provider rejected key" in result


class TestOrdinaryTextSurvives:
    @pytest.mark.parametrize(
        ("label", "text"),
        [
            ("uuid request id", "request_id=3f9a2c1b-8e5d-4a7f-9b2c-1d3e5f7a9b0c"),
            ("bare hex uuid", "3f9a2c1b8e5d4a7f9b2c1d3e5f7a9b0c"),
            ("iso timestamp", "2026-08-24T12:04:23.252994Z"),
            ("dotted module path", "factory_core.application.auth.verification"),
            ("prose", "the deployment completed successfully in 12 seconds"),
            ("structured log line", "worker.started environment=development"),
            ("long snake_case", "this_is_a_very_long_identifier_without_digits"),
            ("file path", "packages/core/src/factory_core/observability/redaction.py"),
        ],
    )
    def test_routine_output_is_not_redacted(self, label: str, text: str) -> None:
        """Each of these appears in real log lines. Redacting any of them would make
        traces unreadable for no security gain."""
        assert REDACTED not in SecretRedactor().redact_text(text)

    def test_correlation_ids_survive_alongside_a_redacted_secret(self) -> None:
        """The realistic case: one log line carrying both."""
        text = (
            "request_id=3f9a2c1b-8e5d-4a7f-9b2c-1d3e5f7a9b0c token=aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF"
        )

        result = SecretRedactor().redact_text(text)

        assert "3f9a2c1b-8e5d-4a7f-9b2c-1d3e5f7a9b0c" in result
        assert "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF" not in result


class TestStrategiesCompose:
    def test_registered_values_still_redact(self) -> None:
        """Entropy detection must not have displaced the exact-match strategy."""
        redactor = SecretRedactor()
        redactor.register("a-registered-low-entropy-value")

        result = redactor.redact_text("using a-registered-low-entropy-value now")

        assert REDACTED in result

    def test_nested_structures_are_redacted_throughout(self) -> None:
        redactor = SecretRedactor()

        result = redactor.redact(
            {
                "request_id": "3f9a2c1b-8e5d-4a7f-9b2c-1d3e5f7a9b0c",
                "nested": {"api_key": "aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF"},
                "items": ["aB3dE6gH9jK2mN5pQ8sT1vW4yZ7bC0eF", "harmless"],
            }
        )

        assert result["request_id"] == "3f9a2c1b-8e5d-4a7f-9b2c-1d3e5f7a9b0c"
        assert result["nested"]["api_key"] == REDACTED
        assert result["items"][0] == REDACTED
        assert result["items"][1] == "harmless"
