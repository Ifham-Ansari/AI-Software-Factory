"""Value encryption: round-trips and fail-closed behaviour [F-201].

The properties the whole vault rests on. Each negative case exists because the positive
case alone would still pass if the implementation silently ignored the key or the
context — a round-trip test cannot tell real encryption from a no-op.

Key management and rotation are in ``test_keyring.py``.
"""

from __future__ import annotations

import base64

import pytest

from factory_core.config.secrets import SecretsSettings
from factory_core.security.envelope import (
    NONCE_LENGTH_BYTES,
    DecryptionError,
    SealedBytes,
    generate_key,
    seal,
    seal_text,
    unseal,
    unseal_text,
    value_context,
)

pytestmark = pytest.mark.unit

PROJECT = "11111111-1111-4111-8111-111111111111"
OTHER_PROJECT = "22222222-2222-4222-8222-222222222222"


def _encoded_key(seed: int) -> str:
    """A deterministic, valid 32-byte key for a given seed."""
    return base64.b64encode(bytes((seed + i) % 256 for i in range(32))).decode("ascii")


def _settings(active: str, previous: str | None = None) -> SecretsSettings:
    return SecretsSettings(_env_file=None, master_key=active, previous_keys=previous)  # type: ignore[arg-type]


class TestValueEncryption:
    def test_round_trip(self) -> None:
        key = generate_key()
        context = value_context(PROJECT, "OPENAI_API_KEY")

        blob = seal_text(key, "sk-a-real-looking-secret", context=context)

        assert unseal_text(key, blob, context=context) == "sk-a-real-looking-secret"

    def test_ciphertext_does_not_contain_the_plaintext(self) -> None:
        """The most basic property, and the one whose absence is catastrophic."""
        key = generate_key()
        secret = "correct-horse-battery-staple"

        blob = seal_text(key, secret, context=value_context(PROJECT, "NAME"))

        assert secret.encode() not in blob

    def test_same_plaintext_encrypts_differently_each_time(self) -> None:
        """A fresh nonce per operation. Identical ciphertexts would leak equality."""
        key = generate_key()
        context = value_context(PROJECT, "NAME")

        first = seal_text(key, "same-value", context=context)
        second = seal_text(key, "same-value", context=context)

        assert first != second

    @pytest.mark.failure
    def test_wrong_key_fails_closed(self) -> None:
        context = value_context(PROJECT, "NAME")
        blob = seal_text(generate_key(), "secret", context=context)

        with pytest.raises(DecryptionError):
            unseal_text(generate_key(), blob, context=context)

    @pytest.mark.security
    def test_ciphertext_cannot_be_moved_to_another_secret_name(self) -> None:
        """AAD binding. Without it, database write access would let an attacker swap a
        low-value credential's ciphertext into a high-value one's row."""
        key = generate_key()
        blob = seal_text(key, "prod-database-password", context=value_context(PROJECT, "DB_URL"))

        with pytest.raises(DecryptionError):
            unseal_text(key, blob, context=value_context(PROJECT, "HARMLESS_FLAG"))

    @pytest.mark.security
    def test_ciphertext_cannot_be_moved_to_another_project(self) -> None:
        key = generate_key()
        blob = seal_text(key, "tenant-a-secret", context=value_context(PROJECT, "TOKEN"))

        with pytest.raises(DecryptionError):
            unseal_text(key, blob, context=value_context(OTHER_PROJECT, "TOKEN"))

    @pytest.mark.failure
    def test_tampered_ciphertext_is_rejected(self) -> None:
        """GCM authenticates. A flipped bit must fail, not decrypt to garbage."""
        key = generate_key()
        context = value_context(PROJECT, "NAME")
        blob = bytearray(seal_text(key, "secret-value", context=context))
        blob[-1] ^= 0x01

        with pytest.raises(DecryptionError):
            unseal_text(key, bytes(blob), context=context)

    @pytest.mark.failure
    def test_truncated_blob_is_rejected(self) -> None:
        with pytest.raises(DecryptionError):
            SealedBytes.from_bytes(b"\x00" * (NONCE_LENGTH_BYTES - 1))

    @pytest.mark.failure
    @pytest.mark.parametrize("length", [0, 16, 31, 33, 64])
    def test_wrong_key_length_is_a_programming_error(self, length: int) -> None:
        """Raised as ValueError, not DecryptionError: a short key is a bug in the
        caller, not a runtime condition to be handled."""
        with pytest.raises(ValueError, match="32 bytes"):
            seal(b"x" * length, b"data", context=b"ctx")

    def test_binary_round_trip(self) -> None:
        key = generate_key()
        payload = bytes(range(256))

        sealed = seal(key, payload, context=b"ctx")

        assert unseal(key, sealed, context=b"ctx") == payload
