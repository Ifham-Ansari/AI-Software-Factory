"""Master-key configuration for envelope encryption.

The key encryption key (KEK) never touches the database. It arrives from the environment
(or a KMS, in a deployment that has one) and wraps the per-project data encryption keys
that actually encrypt secret values.

Keys are **versioned** because rotation has to be possible without a downtime window in
which half the rows cannot be read. The active key wraps new DEKs; previous keys stay
loaded so existing wrapped DEKs still unwrap. Rotation is therefore: add a new active key,
re-wrap at leisure, then drop the old one. See ``docs/runbooks/key-management.md``.

Format is ``<version>:<base64-encoded 32 bytes>`` — for example ``v1:3q2+7w...``. The
version travels with every wrapped DEK, so unwrapping never has to guess which key was
used.
"""

from __future__ import annotations

import base64
import binascii
from typing import Annotated

from pydantic import AliasChoices, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: AES-256 needs exactly 32 bytes of key material.
KEY_LENGTH_BYTES = 32


def decode_key_material(encoded: str) -> bytes:
    """Decode base64 key material, rejecting anything that is not a 32-byte key.

    Raises:
        ValueError: The value is not valid base64, or decodes to the wrong length. Both
            are configuration errors worth failing startup over — a short key silently
            accepted would weaken every secret in the system.
    """
    try:
        material = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        msg = "master key material must be valid base64"
        raise ValueError(msg) from exc
    if len(material) != KEY_LENGTH_BYTES:
        msg = f"master key must decode to {KEY_LENGTH_BYTES} bytes, got {len(material)}"
        raise ValueError(msg)
    return material


def _validate_versioned_key(value: str) -> None:
    """Check one ``version:material`` entry, raising with the offending version named."""
    version, separator, encoded = value.partition(":")
    if not separator or not version.strip():
        msg = "master key must be formatted as '<version>:<base64 key>', e.g. 'v1:...'"
        raise ValueError(msg)
    try:
        decode_key_material(encoded.strip())
    except ValueError as exc:
        msg = f"master key '{version}' is invalid: {exc}"
        raise ValueError(msg) from exc


class SecretsSettings(BaseSettings):
    """Envelope-encryption key material.

    Optional so that a deployment using none of the secret-vault features still starts.
    The vault itself refuses to operate when unconfigured rather than falling back to
    storing values in the clear, which would be the far worse failure.
    """

    model_config = SettingsConfigDict(
        env_prefix="SECRETS__",
        env_file=".env",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    master_key: Annotated[
        SecretStr | None,
        Field(
            validation_alias=AliasChoices("SECRETS__MASTER_KEY", "SECRETS_MASTER_KEY"),
            description="Active KEK as '<version>:<base64 32 bytes>'.",
        ),
    ] = None

    previous_keys: Annotated[
        SecretStr | None,
        Field(
            validation_alias=AliasChoices("SECRETS__PREVIOUS_KEYS", "SECRETS_PREVIOUS_KEYS"),
            description=(
                "Comma-separated retired KEKs, still able to unwrap existing DEKs "
                "during a rotation."
            ),
        ),
    ] = None

    @field_validator("master_key", "previous_keys", mode="before")
    @classmethod
    def _blank_is_unset(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("master_key")
    @classmethod
    def _validate_active(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            _validate_versioned_key(value.get_secret_value().strip())
        return value

    @field_validator("previous_keys")
    @classmethod
    def _validate_previous(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return None
        for entry in value.get_secret_value().split(","):
            if entry.strip():
                _validate_versioned_key(entry.strip())
        return value

    @property
    def is_configured(self) -> bool:
        """Whether the platform can encrypt and decrypt secret values."""
        return self.master_key is not None
