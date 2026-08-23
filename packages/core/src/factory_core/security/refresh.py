"""Refresh tokens: opaque, rotating, with theft detection.

The design in one paragraph: a refresh token is a long random string, never a JWT. Only
its SHA-256 digest is stored, so a database leak does not yield usable sessions. Every
use rotates it — the presented token is revoked and a replacement is issued in the same
*family*. If a token that was already used is presented again, the only explanations are
theft or a cloned client, so the entire family is revoked and the user must sign in
again.

That last rule is what makes rotation worth doing. Rotation alone just moves the secret
around; rotation plus reuse detection means a stolen token is usable at most once before
it locks out both the thief and the victim, and the event is auditable.

SHA-256 is correct here even though passwords need Argon2: a 256-bit random token has no
guessable structure, so there is nothing for a slow hash to defend against, and refresh
happens often enough that speed matters.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from factory_core.domain.ids import TokenFamilyId, TokenId, UserId

# 32 bytes of entropy, URL-safe encoded. Well beyond guessing range.
_TOKEN_BYTES = 32


class RefreshTokenStatus(StrEnum):
    """Why a stored refresh token is or is not usable."""

    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"


class RefreshTokenRecord(BaseModel):
    """The stored half of a refresh token.

    Never contains the token itself — only its digest.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: TokenId
    family_id: TokenFamilyId
    user_id: UserId
    token_hash: str
    status: RefreshTokenStatus
    issued_at: datetime
    expires_at: datetime
    rotated_at: datetime | None = None
    revoked_at: datetime | None = None
    replaced_by_id: TokenId | None = None

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Whether this token is past its expiry."""
        return (now or datetime.now(UTC)) >= self.expires_at

    def is_usable(self, *, now: datetime | None = None) -> bool:
        """Whether this token may be exchanged for a new session."""
        return self.status is RefreshTokenStatus.ACTIVE and not self.is_expired(now=now)


class IssuedRefreshToken(BaseModel):
    """A newly minted refresh token: the secret plus the record to store.

    The plaintext exists only in this object, on the way to the client. It is never
    persisted and never logged.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    token: str = Field(repr=False)
    record: RefreshTokenRecord


def hash_refresh_token(token: str) -> str:
    """Compute the storage digest of a refresh token."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def tokens_match(stored_hash: str, presented_token: str) -> bool:
    """Compare a presented token against a stored digest in constant time.

    ``compare_digest`` avoids leaking how many leading characters matched, which would
    otherwise let an attacker reconstruct a digest one byte at a time.
    """
    return hmac.compare_digest(stored_hash, hash_refresh_token(presented_token))


def generate_refresh_token(
    *,
    user_id: UserId,
    family_id: TokenFamilyId,
    token_id: TokenId,
    ttl_seconds: int,
    now: datetime | None = None,
) -> IssuedRefreshToken:
    """Mint a refresh token and the record that will be stored for it.

    Args:
        user_id: Owner of the session.
        family_id: Session family. A rotation keeps the family; a fresh sign-in starts a
            new one.
        token_id: Identifier for this specific token.
        ttl_seconds: Lifetime in seconds.
        now: Issue time; injectable for tests.
    """
    issued_at = now or datetime.now(UTC)
    secret = secrets.token_urlsafe(_TOKEN_BYTES)
    record = RefreshTokenRecord(
        id=token_id,
        family_id=family_id,
        user_id=user_id,
        token_hash=hash_refresh_token(secret),
        status=RefreshTokenStatus.ACTIVE,
        issued_at=issued_at,
        expires_at=issued_at + timedelta(seconds=ttl_seconds),
    )
    return IssuedRefreshToken(token=secret, record=record)
