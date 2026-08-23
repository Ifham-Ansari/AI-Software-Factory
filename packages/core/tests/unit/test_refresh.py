"""Refresh-token generation, hashing and comparison."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from factory_core.domain.ids import UserId, new_token_family_id, new_token_id
from factory_core.security import (
    RefreshTokenStatus,
    generate_refresh_token,
    hash_refresh_token,
    tokens_match,
)

pytestmark = pytest.mark.unit

TTL = 2_592_000


def _issue(user_id: UserId, *, ttl: int = TTL, now: datetime | None = None):  # type: ignore[no-untyped-def]
    return generate_refresh_token(
        user_id=user_id,
        family_id=new_token_family_id(),
        token_id=new_token_id(),
        ttl_seconds=ttl,
        now=now,
    )


class TestGeneration:
    def test_plaintext_is_not_stored(self, user_id: UserId) -> None:
        """The record persisted to the database must never hold the token itself."""
        issued = _issue(user_id)

        assert issued.token not in issued.record.token_hash
        assert issued.record.token_hash == hash_refresh_token(issued.token)

    def test_tokens_are_unique(self, user_id: UserId) -> None:
        tokens = {_issue(user_id).token for _ in range(50)}

        assert len(tokens) == 50

    def test_token_has_sufficient_entropy(self, user_id: UserId) -> None:
        """32 random bytes, URL-safe encoded, is ~43 characters."""
        assert len(_issue(user_id).token) >= 43

    def test_starts_active(self, user_id: UserId) -> None:
        issued = _issue(user_id)

        assert issued.record.status is RefreshTokenStatus.ACTIVE
        assert issued.record.is_usable()

    def test_expiry_follows_ttl(self, user_id: UserId) -> None:
        now = datetime(2026, 1, 1, tzinfo=UTC)

        issued = _issue(user_id, ttl=3600, now=now)

        assert issued.record.expires_at == now + timedelta(seconds=3600)

    def test_plaintext_hidden_from_repr(self, user_id: UserId) -> None:
        """A refresh token in a traceback or debug log is a session handover."""
        issued = _issue(user_id)

        assert issued.token not in repr(issued)


class TestComparison:
    def test_matching_token_accepted(self, user_id: UserId) -> None:
        issued = _issue(user_id)

        assert tokens_match(issued.record.token_hash, issued.token)

    def test_different_token_rejected(self, user_id: UserId) -> None:
        first = _issue(user_id)
        second = _issue(user_id)

        assert not tokens_match(first.record.token_hash, second.token)

    @pytest.mark.parametrize("wrong", ["", "x", "not-the-token"])
    def test_garbage_rejected(self, user_id: UserId, wrong: str) -> None:
        issued = _issue(user_id)

        assert not tokens_match(issued.record.token_hash, wrong)

    def test_hashing_is_deterministic(self) -> None:
        assert hash_refresh_token("abc") == hash_refresh_token("abc")
        assert hash_refresh_token("abc") != hash_refresh_token("abd")


class TestExpiry:
    def test_expired_token_is_not_usable(self, user_id: UserId) -> None:
        issued = _issue(user_id, ttl=60, now=datetime.now(UTC) - timedelta(hours=1))

        assert issued.record.is_expired()
        assert not issued.record.is_usable()

    def test_expiry_boundary_is_exclusive(self, user_id: UserId) -> None:
        """At exactly the expiry instant the token is already invalid."""
        now = datetime(2026, 1, 1, tzinfo=UTC)
        issued = _issue(user_id, ttl=3600, now=now)

        assert not issued.record.is_expired(now=now + timedelta(seconds=3599))
        assert issued.record.is_expired(now=issued.record.expires_at)

    def test_rotated_token_is_not_usable(self, user_id: UserId) -> None:
        """Rotation is what makes reuse detectable, so a rotated token must be dead."""
        issued = _issue(user_id)
        rotated = issued.record.model_copy(update={"status": RefreshTokenStatus.ROTATED})

        assert not rotated.is_usable()

    def test_revoked_token_is_not_usable(self, user_id: UserId) -> None:
        issued = _issue(user_id)
        revoked = issued.record.model_copy(update={"status": RefreshTokenStatus.REVOKED})

        assert not revoked.is_usable()
