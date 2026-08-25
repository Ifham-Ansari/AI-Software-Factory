"""Envelope encryption primitives.

Two layers, so that no single key compromise exposes everything and so that rotating the
outer key does not require re-encrypting every value:

```
KEK (master key, from config, never stored)
  └── wraps a per-project DEK ── stored wrapped in `project_keys`
        └── encrypts secret values ── AES-256-GCM, fresh nonce per value
```

Every operation is AES-256-GCM, which is *authenticated* encryption: tampering with a
ciphertext makes decryption fail rather than return garbage. Two properties follow, and
both are relied on elsewhere:

* A wrong key fails closed with :class:`DecryptionError`, never a wrong plaintext.
* Ciphertexts are bound to their context through additional authenticated data (AAD).
  A secret row's ciphertext carries its project and name in the AAD, so moving the bytes
  to another row — or another project — makes them undecryptable. Without AAD, an
  attacker with database write access could swap one project's credential into another's.

Nonces are random per operation. GCM's 96-bit nonce makes accidental reuse negligible at
our volumes, and reuse would be catastrophic, so nonces are never derived or counted.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from factory_core.config.secrets import KEY_LENGTH_BYTES
from factory_core.errors import AppError, ErrorCode

#: GCM's standard nonce size. Anything else costs performance and buys nothing.
NONCE_LENGTH_BYTES: Final = 12


class DecryptionError(AppError):
    """Ciphertext could not be decrypted with the supplied key.

    Deliberately says nothing about *why*. Distinguishing "wrong key" from "tampered
    ciphertext" from "wrong context" would tell an attacker which of their guesses was
    closer.
    """

    code = ErrorCode.INTERNAL_ERROR
    status_code = 500
    message = "A stored value could not be decrypted."


@dataclass(frozen=True, slots=True)
class SealedBytes:
    """A nonce and the ciphertext it was produced with.

    Kept together because they are useless apart. Serialised as ``nonce || ciphertext``
    for storage in a single column — a two-column layout invites writing one and not the
    other.
    """

    nonce: bytes
    ciphertext: bytes

    def to_bytes(self) -> bytes:
        """Concatenate for storage."""
        return self.nonce + self.ciphertext

    @classmethod
    def from_bytes(cls, blob: bytes) -> SealedBytes:
        """Split a stored blob back into its parts.

        Raises:
            DecryptionError: The blob is too short to contain a nonce. Raised as a
                decryption failure rather than a ``ValueError`` because to every caller
                this is the same event: the stored value is unusable.
        """
        if len(blob) <= NONCE_LENGTH_BYTES:
            raise DecryptionError
        return cls(nonce=blob[:NONCE_LENGTH_BYTES], ciphertext=blob[NONCE_LENGTH_BYTES:])


def generate_key() -> bytes:
    """Generate 32 bytes of key material from the OS CSPRNG.

    Used for both DEKs and, by the key-generation script, for KEKs.
    """
    return os.urandom(KEY_LENGTH_BYTES)


def seal(key: bytes, plaintext: bytes, *, context: bytes) -> SealedBytes:
    """Encrypt with AES-256-GCM, binding the result to ``context``.

    Args:
        key: 32-byte key.
        plaintext: Data to encrypt.
        context: Additional authenticated data. Not encrypted, but decryption fails
            unless exactly the same value is supplied. Use it to bind a ciphertext to
            where it lives.

    Raises:
        ValueError: ``key`` is not 32 bytes. A programming error, not a runtime condition.
    """
    _require_key_length(key)
    nonce = os.urandom(NONCE_LENGTH_BYTES)
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, context)
    return SealedBytes(nonce=nonce, ciphertext=ciphertext)


def unseal(key: bytes, sealed: SealedBytes, *, context: bytes) -> bytes:
    """Decrypt and verify.

    Raises:
        DecryptionError: The key is wrong, the context does not match, or the ciphertext
            was modified. All three are indistinguishable by design.
        ValueError: ``key`` is not 32 bytes.
    """
    _require_key_length(key)
    try:
        return AESGCM(key).decrypt(sealed.nonce, sealed.ciphertext, context)
    except InvalidTag as exc:
        raise DecryptionError from exc


def seal_text(key: bytes, plaintext: str, *, context: bytes) -> bytes:
    """Encrypt a string, returning a single storable blob."""
    return seal(key, plaintext.encode("utf-8"), context=context).to_bytes()


def unseal_text(key: bytes, blob: bytes, *, context: bytes) -> str:
    """Decrypt a blob produced by :func:`seal_text`.

    Raises:
        DecryptionError: Decryption failed, or the plaintext was not valid UTF-8 — which
            means it was not written by :func:`seal_text` and is equally unusable.
    """
    plaintext = unseal(key, SealedBytes.from_bytes(blob), context=context)
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise DecryptionError from exc


def value_context(project_id: str, name: str) -> bytes:
    """Build the AAD binding a secret value to its project and name.

    Both components are included so that a ciphertext is usable only in the exact row it
    was written for. Renaming a secret therefore requires re-encrypting it, which is the
    correct trade: silent cross-row reuse is the thing being prevented.
    """
    return f"secret:{project_id}:{name}".encode()


def dek_context(project_id: str) -> bytes:
    """Build the AAD binding a wrapped DEK to its project."""
    return f"dek:{project_id}".encode()


def _require_key_length(key: bytes) -> None:
    if len(key) != KEY_LENGTH_BYTES:
        msg = f"key must be {KEY_LENGTH_BYTES} bytes, got {len(key)}"
        raise ValueError(msg)
