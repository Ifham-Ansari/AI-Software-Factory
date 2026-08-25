"""Secret reference parsing and the resolution guards [F-203].

The guards are the security-relevant part: a reference is inert, and turning one into a
value requires an allowlisted sink outside a traced context. Both refusals are tested
here; the audit trail that accompanies them is tested against a real database in the
integration suite.
"""

from __future__ import annotations

import pytest

from factory_core.security.references import (
    InvalidSecretReferenceError,
    SecretReference,
    SecretSink,
    SinkNotAllowedError,
    TracedContextError,
    ensure_resolvable,
    in_traced_context,
    is_secret_reference,
    is_valid_secret_name,
    traced_context,
)

pytestmark = pytest.mark.unit

PROJECT = "11111111-1111-4111-8111-111111111111"


class TestReferenceFormat:
    def test_round_trip(self) -> None:
        reference = SecretReference.build(PROJECT, "OPENAI_API_KEY")

        assert str(reference) == f"secret://project/{PROJECT}/OPENAI_API_KEY"
        assert SecretReference.parse(str(reference)) == reference

    def test_parse_tolerates_surrounding_whitespace(self) -> None:
        """References travel through YAML and LLM output; both add whitespace."""
        parsed = SecretReference.parse(f"  secret://project/{PROJECT}/TOKEN  ")

        assert parsed.name == "TOKEN"

    @pytest.mark.failure
    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "not-a-reference",
            "https://project/x/NAME",
            "secret://project/not-a-uuid/NAME",
            f"secret://project/{PROJECT}/lowercase",
            f"secret://project/{PROJECT}/WITH-HYPHEN",
            f"secret://other/{PROJECT}/NAME",
            f"secret://project/{PROJECT}/",
        ],
    )
    def test_malformed_references_are_rejected(self, raw: str) -> None:
        with pytest.raises(InvalidSecretReferenceError):
            SecretReference.parse(raw)

    @pytest.mark.security
    def test_error_does_not_echo_the_input(self) -> None:
        """A malformed reference can come from an LLM. Echoing it into an error body is
        a needless injection surface."""
        hostile = "secret://project/x/<script>alert(1)</script>"

        with pytest.raises(InvalidSecretReferenceError) as exc_info:
            SecretReference.parse(hostile)

        assert "script" not in exc_info.value.message

    @pytest.mark.failure
    @pytest.mark.parametrize("name", ["lower", "1LEADING_DIGIT", "HAS-HYPHEN", "", "A" * 65])
    def test_invalid_names_are_refused_when_building(self, name: str) -> None:
        with pytest.raises(InvalidSecretReferenceError):
            SecretReference.build(PROJECT, name)

    @pytest.mark.parametrize("name", ["A", "DATABASE_URL", "X9", "A_B_C_1"])
    def test_valid_names_accepted(self, name: str) -> None:
        assert is_valid_secret_name(name)

    def test_is_secret_reference_detects_the_scheme(self) -> None:
        assert is_secret_reference(f"secret://project/{PROJECT}/NAME")
        assert not is_secret_reference("an-actual-secret-value")
        assert not is_secret_reference(None)
        assert not is_secret_reference(42)


class TestResolutionGuards:
    @pytest.mark.parametrize("sink", list(SecretSink))
    def test_every_allowlisted_sink_is_permitted(self, sink: SecretSink) -> None:
        ensure_resolvable(sink)  # must not raise

    @pytest.mark.security
    @pytest.mark.failure
    @pytest.mark.parametrize("sink", ["provider_env", "arbitrary_sink", None, 42])
    def test_non_member_sinks_are_refused(self, sink: object) -> None:
        """A plain string is refused even when it spells an allowlisted value. Membership
        of the enum is the check, so a caller cannot invent a sink at a call site."""
        with pytest.raises(SinkNotAllowedError):
            ensure_resolvable(sink)  # type: ignore[arg-type]

    @pytest.mark.security
    def test_resolution_is_refused_inside_a_traced_context(self) -> None:
        """Phase 3 ships prompts and tool I/O to LangSmith. A plaintext credential
        resolved inside a traced span is one serialisation from a third party."""
        with traced_context(), pytest.raises(TracedContextError):
            ensure_resolvable(SecretSink.PROVIDER_ENV)

    def test_the_traced_flag_is_scoped_to_its_block(self) -> None:
        assert not in_traced_context()
        with traced_context():
            assert in_traced_context()
        assert not in_traced_context()

    def test_traced_flag_is_restored_after_an_exception(self) -> None:
        """A raising span must not leave every later resolution refused."""
        with pytest.raises(RuntimeError), traced_context():
            raise RuntimeError

        assert not in_traced_context()
        ensure_resolvable(SecretSink.SANDBOX_ENV)
