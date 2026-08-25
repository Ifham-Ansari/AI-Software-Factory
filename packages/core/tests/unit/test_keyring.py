"""Master keys and the key ring [F-201].

Split from ``test_envelope_crypto.py`` (value encryption) because this is the *key
management* half: parsing configuration, wrapping a per-project DEK, and rotating the
outer key without invalidating anything it protects.

The rotation tests are the load-bearing ones. Rotating the KEK must leave every value the
DEK encrypts readable — that is the entire reason for two layers rather than one.
"""

from __future__ import annotations

import base64

import pytest

from factory_core.config.secrets import SecretsSettings, decode_key_material
from factory_core.errors import ConfigurationError
from factory_core.security.envelope import (
    DecryptionError,
    dek_context,
    generate_key,
    seal_text,
    unseal_text,
    value_context,
)
from factory_core.security.keyring import KeyRing, MasterKey, build_keyring

pytestmark = pytest.mark.unit

PROJECT = "11111111-1111-4111-8111-111111111111"
OTHER_PROJECT = "22222222-2222-4222-8222-222222222222"


def _encoded_key(seed: int) -> str:
    """A deterministic, valid 32-byte key for a given seed."""
    return base64.b64encode(bytes((seed + i) % 256 for i in range(32))).decode("ascii")


def _settings(active: str, previous: str | None = None) -> SecretsSettings:
    return SecretsSettings(_env_file=None, master_key=active, previous_keys=previous)  # type: ignore[arg-type]


class TestKeyMaterialParsing:
    def test_valid_key_decodes(self) -> None:
        assert len(decode_key_material(_encoded_key(0))) == 32

    @pytest.mark.failure
    def test_non_base64_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="base64"):
            decode_key_material("not-valid-base64!!!")

    @pytest.mark.failure
    def test_wrong_length_is_rejected(self) -> None:
        """A 16-byte key would silently give AES-128 instead of AES-256."""
        short = base64.b64encode(b"x" * 16).decode("ascii")

        with pytest.raises(ValueError, match="32 bytes"):
            decode_key_material(short)

    @pytest.mark.failure
    @pytest.mark.parametrize("value", ["v1", "novalue:", ":abc", "v1:short"])
    def test_malformed_configuration_is_refused(self, value: str) -> None:
        with pytest.raises(ValueError, match=r"\S"):
            SecretsSettings(_env_file=None, master_key=value)  # type: ignore[arg-type]

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_means_unconfigured_not_invalid(self, blank: str) -> None:
        """A template ships ``SECRETS__MASTER_KEY=``; that means "no vault", not "broken
        vault". Consistent with every other optional setting in this codebase."""
        settings = SecretsSettings(_env_file=None, master_key=blank)  # type: ignore[arg-type]

        assert not settings.is_configured


class TestKeyRing:
    def test_wrap_and_unwrap(self) -> None:
        ring = build_keyring(_settings(f"v1:{_encoded_key(0)}"))
        dek = ring.generate_dek()

        wrapped = ring.wrap_dek(dek, project_id=PROJECT)

        assert wrapped.startswith("v1:")
        assert ring.unwrap_dek(wrapped, project_id=PROJECT) == dek

    @pytest.mark.security
    def test_wrapped_dek_is_bound_to_its_project(self) -> None:
        ring = build_keyring(_settings(f"v1:{_encoded_key(0)}"))
        wrapped = ring.wrap_dek(ring.generate_dek(), project_id=PROJECT)

        with pytest.raises(DecryptionError):
            ring.unwrap_dek(wrapped, project_id=OTHER_PROJECT)

    @pytest.mark.failure
    def test_unknown_version_fails_closed(self) -> None:
        """What happens when a key is dropped from configuration too early."""
        old = build_keyring(_settings(f"v1:{_encoded_key(0)}"))
        wrapped = old.wrap_dek(old.generate_dek(), project_id=PROJECT)
        without_v1 = build_keyring(_settings(f"v2:{_encoded_key(90)}"))

        with pytest.raises(DecryptionError):
            without_v1.unwrap_dek(wrapped, project_id=PROJECT)

    @pytest.mark.failure
    @pytest.mark.parametrize("wrapped", ["", "v1", "v1:!!!notbase64", "no-separator"])
    def test_malformed_wrapped_dek_fails_closed(self, wrapped: str) -> None:
        ring = build_keyring(_settings(f"v1:{_encoded_key(0)}"))

        with pytest.raises(DecryptionError):
            ring.unwrap_dek(wrapped, project_id=PROJECT)

    def test_rotation_preserves_access_to_existing_values(self) -> None:
        """The acceptance criterion for F-201: rotation must not orphan stored data."""
        v1 = build_keyring(_settings(f"v1:{_encoded_key(0)}"))
        dek = v1.generate_dek()
        wrapped_v1 = v1.wrap_dek(dek, project_id=PROJECT)
        context = value_context(PROJECT, "API_KEY")
        blob = seal_text(dek, "value-encrypted-before-rotation", context=context)

        rotated = build_keyring(_settings(f"v2:{_encoded_key(90)}", f"v1:{_encoded_key(0)}"))
        rewrapped = rotated.rewrap_dek(wrapped_v1, project_id=PROJECT)

        assert rewrapped.startswith("v2:")
        # The DEK survives the rotation, so values encrypted under it still decrypt.
        recovered_dek = rotated.unwrap_dek(rewrapped, project_id=PROJECT)
        assert recovered_dek == dek
        assert unseal_text(recovered_dek, blob, context=context) == (
            "value-encrypted-before-rotation"
        )

    def test_needs_rewrap_identifies_retired_versions(self) -> None:
        v1 = build_keyring(_settings(f"v1:{_encoded_key(0)}"))
        wrapped_v1 = v1.wrap_dek(v1.generate_dek(), project_id=PROJECT)
        rotated = build_keyring(_settings(f"v2:{_encoded_key(90)}", f"v1:{_encoded_key(0)}"))

        assert rotated.needs_rewrap(wrapped_v1)
        assert not rotated.needs_rewrap(rotated.rewrap_dek(wrapped_v1, project_id=PROJECT))

    def test_known_versions_includes_previous(self) -> None:
        ring = build_keyring(_settings(f"v2:{_encoded_key(90)}", f"v1:{_encoded_key(0)}"))

        assert ring.known_versions == {"v1", "v2"}
        assert ring.active_version == "v2"

    @pytest.mark.failure
    def test_duplicate_versions_are_refused(self) -> None:
        """Silently preferring one would make unwrapping order-dependent."""
        with pytest.raises(ConfigurationError, match="duplicate"):
            KeyRing(
                MasterKey("v1", generate_key()),
                (MasterKey("v1", generate_key()),),
            )

    @pytest.mark.failure
    def test_unconfigured_keyring_refuses_to_build(self) -> None:
        """Failing loudly beats falling back to storing values in the clear.

        ``master_key=None`` is passed explicitly, not merely left unset: the root conftest
        loads ``.env`` into ``os.environ``, and an environment variable beats
        ``_env_file=None``. A developer with a key configured would otherwise find this
        test asserting the opposite of what it says.
        """
        unconfigured = SecretsSettings(_env_file=None, master_key=None)  # type: ignore[call-arg]
        assert not unconfigured.is_configured

        with pytest.raises(ConfigurationError, match="SECRETS__MASTER_KEY"):
            build_keyring(unconfigured)

    def test_dek_context_differs_per_project(self) -> None:
        assert dek_context(PROJECT) != dek_context(OTHER_PROJECT)
