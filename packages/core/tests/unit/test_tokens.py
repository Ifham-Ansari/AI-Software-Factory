"""Access token issuing and verification."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
import pytest

from factory_core.domain.ids import UserId
from factory_core.errors import TokenExpiredError, TokenInvalidError
from factory_core.security import AccessTokenIssuer

pytestmark = pytest.mark.unit


class TestIssuing:
    def test_round_trip(self, token_issuer: AccessTokenIssuer, user_id: UserId) -> None:
        claims = token_issuer.verify(token_issuer.issue(user_id))

        assert claims.user_id == user_id
        assert claims.typ == "access"

    def test_each_token_is_unique(self, token_issuer: AccessTokenIssuer, user_id: UserId) -> None:
        """A distinct jti per token is what makes individual revocation possible later."""
        first = token_issuer.verify(token_issuer.issue(user_id))
        second = token_issuer.verify(token_issuer.issue(user_id))

        assert first.jti != second.jti

    def test_expiry_follows_configured_ttl(self, user_id: UserId) -> None:
        issuer = AccessTokenIssuer(secret_key="k" * 40, issuer="i", audience="a", ttl_seconds=900)

        claims = issuer.verify(issuer.issue(user_id, now=datetime.now(UTC)))

        assert claims.exp - claims.iat == 900

    def test_default_ttl_is_ten_minutes(self, token_issuer: AccessTokenIssuer) -> None:
        """Short-lived by design: revocation is handled by the stateful refresh token."""
        assert token_issuer.ttl_seconds == 600


@pytest.mark.failure
class TestVerificationFailures:
    def test_expired_token_rejected(self, token_issuer: AccessTokenIssuer, user_id: UserId) -> None:
        past = datetime.now(UTC) - timedelta(hours=2)

        with pytest.raises(TokenExpiredError):
            token_issuer.verify(token_issuer.issue(user_id, now=past))

    def test_tampered_payload_rejected(
        self, token_issuer: AccessTokenIssuer, user_id: UserId
    ) -> None:
        token = token_issuer.issue(user_id)
        header, payload, signature = token.split(".")
        forged = f"{header}.{payload[:-4]}AAAA.{signature}"

        with pytest.raises(TokenInvalidError):
            token_issuer.verify(forged)

    def test_wrong_signing_key_rejected(self, user_id: UserId) -> None:
        attacker = AccessTokenIssuer(
            secret_key="z" * 40, issuer="test-issuer", audience="test-audience"
        )
        defender = AccessTokenIssuer(
            secret_key="k" * 40, issuer="test-issuer", audience="test-audience"
        )

        with pytest.raises(TokenInvalidError):
            defender.verify(attacker.issue(user_id))

    def test_wrong_audience_rejected(
        self, token_issuer: AccessTokenIssuer, user_id: UserId
    ) -> None:
        other = AccessTokenIssuer(
            secret_key="test-secret-key-that-is-long-enough-for-hs256",
            issuer="test-issuer",
            audience="a-different-service",
        )

        with pytest.raises(TokenInvalidError):
            token_issuer.verify(other.issue(user_id))

    def test_wrong_issuer_rejected(self, token_issuer: AccessTokenIssuer, user_id: UserId) -> None:
        other = AccessTokenIssuer(
            secret_key="test-secret-key-that-is-long-enough-for-hs256",
            issuer="someone-else",
            audience="test-audience",
        )

        with pytest.raises(TokenInvalidError):
            token_issuer.verify(other.issue(user_id))

    @pytest.mark.parametrize("garbage", ["", "not.a.token", "a.b", "...", "Bearer xyz"])
    def test_malformed_token_rejected(self, token_issuer: AccessTokenIssuer, garbage: str) -> None:
        with pytest.raises(TokenInvalidError):
            token_issuer.verify(garbage)

    def test_unsigned_token_rejected(self, user_id: UserId) -> None:
        """The classic `alg: none` downgrade must not be accepted."""
        forged = jwt.encode(
            {
                "sub": str(user_id),
                "jti": "x",
                "typ": "access",
                "iss": "test-issuer",
                "aud": "test-audience",
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int((datetime.now(UTC) + timedelta(hours=1)).timestamp()),
            },
            key="",
            algorithm="none",
        )
        issuer = AccessTokenIssuer(
            secret_key="test-secret-key-that-is-long-enough-for-hs256",
            issuer="test-issuer",
            audience="test-audience",
        )

        with pytest.raises(TokenInvalidError):
            issuer.verify(forged)

    def test_missing_required_claim_rejected(self) -> None:
        secret = "test-secret-key-that-is-long-enough-for-hs256"
        issuer = AccessTokenIssuer(
            secret_key=secret, issuer="test-issuer", audience="test-audience"
        )
        incomplete = jwt.encode(
            {"iss": "test-issuer", "aud": "test-audience", "typ": "access"},
            secret,
            algorithm="HS256",
        )

        with pytest.raises(TokenInvalidError):
            issuer.verify(incomplete)

    def test_non_uuid_subject_rejected(self) -> None:
        secret = "test-secret-key-that-is-long-enough-for-hs256"
        issuer = AccessTokenIssuer(
            secret_key=secret, issuer="test-issuer", audience="test-audience"
        )
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": "admin",
                "jti": "x",
                "typ": "access",
                "iss": "test-issuer",
                "aud": "test-audience",
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(hours=1)).timestamp()),
            },
            secret,
            algorithm="HS256",
        )

        with pytest.raises(TokenInvalidError):
            issuer.verify(token)
