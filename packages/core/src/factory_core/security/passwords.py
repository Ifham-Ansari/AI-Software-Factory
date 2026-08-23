"""Password hashing with Argon2id.

Argon2id is the current OWASP recommendation: memory-hard, so commodity GPU and ASIC
attacks lose most of their advantage over a defender's CPU.

Parameters are configuration rather than constants because the right cost depends on the
hardware the API runs on. Defaults follow OWASP's second recommended configuration
(19 MiB, t=2, p=1), which lands near 50 ms on typical server hardware — slow enough to
matter to an attacker, fast enough that a login feels instant.
"""

from __future__ import annotations

from argon2 import PasswordHasher as Argon2Hasher
from argon2 import Type
from argon2.exceptions import (
    HashingError,
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)

# A precomputed hash of a value no user can hold, used to spend the same CPU time on a
# failed lookup as on a real verification. See `verify_dummy`.
_DUMMY_PASSWORD = "not-a-real-password-used-only-for-timing-equalisation"  # noqa: S105


class PasswordHasher:
    """Hashes and verifies passwords.

    Instances are cheap; one is normally built at startup from settings and injected.
    """

    def __init__(
        self,
        *,
        time_cost: int = 2,
        memory_cost_kib: int = 19_456,
        parallelism: int = 1,
    ) -> None:
        self._hasher = Argon2Hasher(
            time_cost=time_cost,
            memory_cost=memory_cost_kib,
            parallelism=parallelism,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash = self._hasher.hash(_DUMMY_PASSWORD)

    def hash(self, password: str) -> str:
        """Hash a plaintext password.

        Returns:
            An encoded Argon2id hash containing the salt and parameters.

        Raises:
            HashingError: The underlying library could not produce a hash.
        """
        return self._hasher.hash(password)

    def verify(self, password_hash: str, password: str) -> bool:
        """Check a password against a stored hash.

        Returns ``False`` rather than raising for every failure mode — wrong password,
        corrupt hash, unsupported algorithm — because the caller's response must be
        identical in all of them. A distinguishable error would reveal which stored
        hashes are malformed.
        """
        try:
            self._hasher.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError, HashingError):
            return False
        return True

    def verify_dummy(self) -> None:
        """Spend hashing time without a real hash.

        Sign-in must take the same time whether or not the email exists. Without this,
        the difference between "no such user" (fast) and "wrong password" (slow) is
        measurable over the network and enumerates registered accounts.
        """
        try:
            self._hasher.verify(self._dummy_hash, _DUMMY_PASSWORD + "x")
        except (VerifyMismatchError, VerificationError, InvalidHashError, HashingError):
            return

    def needs_rehash(self, password_hash: str) -> bool:
        """Whether a stored hash was made with weaker parameters than current settings.

        Callers rehash on successful sign-in, which upgrades stored hashes over time
        without forcing a password reset.
        """
        try:
            return self._hasher.check_needs_rehash(password_hash)
        except (InvalidHashError, VerificationError):
            return True
