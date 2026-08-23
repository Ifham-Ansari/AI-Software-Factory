"""JWT access tokens.

Access tokens are short-lived (10 minutes by default) and stateless: the API verifies a
signature rather than hitting the database on every request. The cost of statelessness is
that revocation is not immediate, which is exactly why the lifetime is short and why the
long-lived half of the session is the *stateful* refresh token in ``refresh.py``.

Claims are validated as a Pydantic model rather than being read out of a raw dict, so a
token missing ``sub`` fails at the boundary instead of producing ``None`` somewhere deep
in a request handler.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import jwt
from pydantic import BaseModel, ConfigDict, ValidationError

from factory_core.domain.ids import UserId
from factory_core.errors import TokenExpiredError, TokenInvalidError

TokenType = Literal["access"]


class AccessTokenClaims(BaseModel):
    """Validated claims carried by an access token."""

    model_config = ConfigDict(extra="ignore")

    sub: str
    jti: str
    typ: TokenType
    iss: str
    aud: str
    iat: int
    exp: int

    @property
    def user_id(self) -> UserId | None:
        """The subject as a ``UserId``, or ``None`` when it is not a UUID."""
        try:
            return UserId(uuid.UUID(self.sub))
        except (ValueError, AttributeError, TypeError):
            return None


class AccessTokenIssuer:
    """Issues and verifies access tokens.

    One instance is built at startup from settings and injected where needed.
    """

    def __init__(
        self,
        *,
        secret_key: str,
        algorithm: str = "HS256",
        issuer: str,
        audience: str,
        ttl_seconds: int = 600,
    ) -> None:
        self._secret = secret_key
        self._algorithm = algorithm
        self._issuer = issuer
        self._audience = audience
        self._ttl = timedelta(seconds=ttl_seconds)

    @property
    def ttl_seconds(self) -> int:
        """Access-token lifetime in seconds."""
        return int(self._ttl.total_seconds())

    def issue(self, user_id: UserId, *, now: datetime | None = None) -> str:
        """Mint an access token for a user.

        Args:
            user_id: Subject of the token.
            now: Issue time; injectable so tests can control expiry without sleeping.
        """
        issued_at = now or datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "jti": uuid.uuid4().hex,
            "typ": "access",
            "iss": self._issuer,
            "aud": self._audience,
            "iat": int(issued_at.timestamp()),
            "exp": int((issued_at + self._ttl).timestamp()),
        }
        return jwt.encode(payload, self._secret, algorithm=self._algorithm)

    def verify(self, token: str) -> AccessTokenClaims:
        """Verify a token's signature and claims.

        Returns:
            The validated claims.

        Raises:
            TokenExpiredError: The token is past its expiry.
            TokenInvalidError: The signature, issuer, audience, structure, or token type
                is wrong.
        """
        try:
            raw = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                audience=self._audience,
                options={"require": ["exp", "iat", "sub", "iss", "aud"]},
            )
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError from exc
        except jwt.InvalidTokenError as exc:
            # Covers bad signature, wrong issuer/audience, malformed structure and
            # missing required claims. All are indistinguishable to the caller by design.
            raise TokenInvalidError from exc

        try:
            claims = AccessTokenClaims.model_validate(raw)
        except ValidationError as exc:
            raise TokenInvalidError from exc

        if claims.user_id is None:
            raise TokenInvalidError("The token subject is not a valid identifier.")
        return claims
