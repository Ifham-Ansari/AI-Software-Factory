"""Master-key handling and DEK wrapping.

The :class:`KeyRing` holds the active key encryption key plus any retired ones. Wrapping
always uses the active key; unwrapping selects by the version recorded alongside the
wrapped DEK. That asymmetry is what makes rotation a background task rather than an outage:

1. Add a new key as active, move the old one to ``SECRETS__PREVIOUS_KEYS``.
2. Existing projects keep working — their DEKs unwrap with the retired key.
3. Re-wrap each project's DEK with the active key, at whatever pace suits.
4. Once no ``project_keys`` row references the old version, drop it from configuration.

A wrapped DEK is stored as ``<version>:<base64(nonce || ciphertext)>``. The version is
outside the ciphertext because it must be readable *before* choosing a key to decrypt with.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass

from factory_core.config.secrets import SecretsSettings, decode_key_material
from factory_core.errors import ConfigurationError
from factory_core.security.envelope import (
    DecryptionError,
    SealedBytes,
    dek_context,
    generate_key,
    seal,
    unseal,
)


@dataclass(frozen=True, slots=True)
class MasterKey:
    """One versioned key encryption key."""

    version: str
    material: bytes

    @classmethod
    def parse(cls, entry: str) -> MasterKey:
        """Parse a ``<version>:<base64 material>`` entry.

        Raises:
            ConfigurationError: The entry is malformed. Surfaced as a configuration
                error because that is what it is — the process should refuse to start.
        """
        version, separator, encoded = entry.partition(":")
        if not separator or not version.strip():
            msg = "master key must be formatted as '<version>:<base64 key>'"
            raise ConfigurationError(msg)
        try:
            material = decode_key_material(encoded.strip())
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        return cls(version=version.strip(), material=material)


class KeyRing:
    """The active KEK plus retired ones, for wrapping and unwrapping DEKs."""

    def __init__(self, active: MasterKey, previous: tuple[MasterKey, ...] = ()) -> None:
        """Bind a key ring.

        Raises:
            ConfigurationError: Two keys share a version. Silently preferring one would
                make unwrapping depend on dictionary ordering.
        """
        keys = (active, *previous)
        versions = [key.version for key in keys]
        if len(set(versions)) != len(versions):
            msg = f"duplicate master key versions in configuration: {sorted(versions)}"
            raise ConfigurationError(msg)
        self._active = active
        self._by_version = {key.version: key for key in keys}

    @property
    def active_version(self) -> str:
        """The version new DEKs are wrapped with."""
        return self._active.version

    @property
    def known_versions(self) -> frozenset[str]:
        """Every version this ring can unwrap."""
        return frozenset(self._by_version)

    def generate_dek(self) -> bytes:
        """Generate a fresh per-project data encryption key."""
        return generate_key()

    def wrap_dek(self, dek: bytes, *, project_id: str) -> str:
        """Wrap a DEK with the active KEK, bound to its project.

        Returns:
            ``<version>:<base64(nonce || ciphertext)>``, ready to store.
        """
        sealed = seal(self._active.material, dek, context=dek_context(project_id))
        encoded = base64.b64encode(sealed.to_bytes()).decode("ascii")
        return f"{self._active.version}:{encoded}"

    def unwrap_dek(self, wrapped: str, *, project_id: str) -> bytes:
        """Unwrap a stored DEK.

        Raises:
            DecryptionError: The version is unknown to this ring, the payload is
                malformed, or it does not belong to this project. An unknown version
                usually means a key was dropped from configuration before every row
                referencing it was re-wrapped.
        """
        version, separator, encoded = wrapped.partition(":")
        key = self._by_version.get(version)
        if not separator or key is None:
            raise DecryptionError
        try:
            blob = base64.b64decode(encoded, validate=True)
        except (ValueError, TypeError) as exc:
            raise DecryptionError from exc
        return unseal(key.material, SealedBytes.from_bytes(blob), context=dek_context(project_id))

    def needs_rewrap(self, wrapped: str) -> bool:
        """Whether a stored DEK was wrapped with a retired key.

        Drives the rotation sweep: anything returning ``True`` still needs re-wrapping
        before its key can be removed from configuration.
        """
        version, separator, _ = wrapped.partition(":")
        return bool(separator) and version != self._active.version

    def rewrap_dek(self, wrapped: str, *, project_id: str) -> str:
        """Re-wrap a DEK under the active key, without changing the DEK itself.

        The DEK is unchanged on purpose: rotating the KEK must not invalidate the values
        the DEK encrypts, which is the entire point of the two-layer design.
        """
        dek = self.unwrap_dek(wrapped, project_id=project_id)
        return self.wrap_dek(dek, project_id=project_id)


def build_keyring(settings: SecretsSettings) -> KeyRing:
    """Construct a key ring from configuration.

    Raises:
        ConfigurationError: No master key is configured. Callers that can operate without
            the vault should check ``settings.is_configured`` first; everything else
            should fail loudly rather than fall back to storing values in the clear.
    """
    if settings.master_key is None:
        msg = (
            "SECRETS__MASTER_KEY is required to store or read secrets. "
            "Generate one with: uv run python scripts/generate_master_key.py"
        )
        raise ConfigurationError(msg)

    active = MasterKey.parse(settings.master_key.get_secret_value().strip())
    previous: list[MasterKey] = []
    if settings.previous_keys is not None:
        for entry in settings.previous_keys.get_secret_value().split(","):
            if entry.strip():
                previous.append(MasterKey.parse(entry.strip()))
    return KeyRing(active, tuple(previous))
