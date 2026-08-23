"""One-time email verification codes.

A six-digit code carries roughly 20 bits of entropy, which is not much. Three things make
it safe enough:

* **Attempt limits.** Six wrong guesses destroys the code. With 10^6 possibilities that
  leaves about a 1-in-166,000 chance per issued code, and the attacker has to start over.
* **Short expiry.** Ten minutes bounds how long a code intercepted in transit is useful.
* **Single use.** A consumed code is dead even inside its window.

The stored form is a SHA-256 digest, like refresh tokens. That is not brute-force
protection — a million-candidate space falls instantly offline — but it keeps live codes
out of a database dump, a backup, or a support engineer's query result. The real defence
is the three properties above.

``secrets.randbelow`` rather than ``random``: the latter is a Mersenne Twister whose future
output is predictable from past output, which for a security code is disqualifying.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from factory_core.domain.ids import UserId, VerificationId


class VerificationStatus(StrEnum):
    """Why a code is or is not usable."""

    PENDING = "pending"
    CONSUMED = "consumed"
    EXPIRED = "expired"
    EXHAUSTED = "exhausted"


class VerificationCode(BaseModel):
    """The stored half of a verification code. Never contains the code itself."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: VerificationId
    user_id: UserId
    code_hash: str
    status: VerificationStatus
    attempts: int = Field(ge=0)
    max_attempts: int = Field(gt=0)
    issued_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Whether this code is past its expiry."""
        return (now or datetime.now(UTC)) >= self.expires_at

    def attempts_remaining(self) -> int:
        """How many wrong guesses are left before the code is destroyed."""
        return max(0, self.max_attempts - self.attempts)

    def is_usable(self, *, now: datetime | None = None) -> bool:
        """Whether this code may still be redeemed."""
        return (
            self.status is VerificationStatus.PENDING
            and not self.is_expired(now=now)
            and self.attempts_remaining() > 0
        )


class IssuedVerificationCode(BaseModel):
    """A newly minted code: the plaintext to email, plus the record to store.

    The plaintext exists only in this object, on its way to the mail transport. It is
    never persisted, and ``repr=False`` keeps it out of tracebacks.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(repr=False)
    record: VerificationCode


def generate_code(length: int = 6) -> str:
    """Generate a numeric code of the given length.

    Zero-padded so every code has the same number of digits — a variable-length code leaks
    a little information and confuses users typing it.
    """
    upper = 10**length
    return str(secrets.randbelow(upper)).zfill(length)


def hash_code(code: str) -> str:
    """Compute the storage digest of a code."""
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def codes_match(stored_hash: str, presented_code: str) -> bool:
    """Compare a presented code against a stored digest in constant time.

    ``compare_digest`` avoids leaking how many leading characters matched, which would
    otherwise let an attacker recover the digest one byte at a time.
    """
    return hmac.compare_digest(stored_hash, hash_code(presented_code))


def issue_verification_code(
    *,
    verification_id: VerificationId,
    user_id: UserId,
    code_length: int,
    ttl_seconds: int,
    max_attempts: int,
    now: datetime | None = None,
) -> IssuedVerificationCode:
    """Mint a code and the record that will be stored for it."""
    issued_at = now or datetime.now(UTC)
    code = generate_code(code_length)
    record = VerificationCode(
        id=verification_id,
        user_id=user_id,
        code_hash=hash_code(code),
        status=VerificationStatus.PENDING,
        attempts=0,
        max_attempts=max_attempts,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )
    return IssuedVerificationCode(code=code, record=record)
