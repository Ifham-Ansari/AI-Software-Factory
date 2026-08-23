"""Ports: the interfaces the application layer depends on.

Protocols rather than base classes, so an adapter satisfies a port by shape alone and
never needs to import from here. Tests supply fakes that are ordinary classes.

``AuthProvider`` exists because authentication is the piece most likely to be replaced.
Today it is backend-owned (Argon2id plus rotating refresh tokens). If an OIDC provider is
adopted later, it implements this protocol and no call site changes — see
architecture.md §15 for why that decision went the way it did.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from factory_core.domain.entities import User


@runtime_checkable
class Clock(Protocol):
    """Source of the current time.

    Injected so tests can control time without sleeping or patching ``datetime``.
    """

    def now(self) -> datetime:
        """Return the current time as a timezone-aware datetime."""
        ...


class SystemClock:
    """The real clock."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        return datetime.now(UTC)


class FrozenClock:
    """A clock stuck at a fixed instant, advanced explicitly.

    Lives in production code rather than a test helper module because the token
    expiry tests in ``packages/api`` need it too, and duplicating it would let the two
    copies drift.
    """

    def __init__(self, at: datetime) -> None:
        self._at = at

    def now(self) -> datetime:
        """Return the frozen instant."""
        return self._at

    def advance(self, seconds: float) -> None:
        """Move the clock forward.

        Args:
            seconds: How far to advance. Must be positive; time does not run backwards.
        """
        if seconds < 0:
            msg = "FrozenClock cannot move backwards"
            raise ValueError(msg)
        self._at = self._at + timedelta(seconds=seconds)


@runtime_checkable
class AuthProvider(Protocol):
    """Establishes and refreshes authenticated sessions."""

    async def register(self, email: str, password: str, display_name: str) -> object:
        """Create an account and return a session."""
        ...

    async def sign_in(self, email: str, password: str) -> object:
        """Authenticate credentials and return a session."""
        ...

    async def refresh(self, refresh_token: str) -> object:
        """Exchange a refresh token for a new session."""
        ...

    async def sign_out(self, refresh_token: str) -> None:
        """Revoke a session."""
        ...


@runtime_checkable
class UserResolver(Protocol):
    """Resolves an access-token subject to a user.

    Narrower than the full user repository on purpose: request authentication needs one
    lookup and should not be handed the ability to write accounts.
    """

    async def resolve(self, user_id: str) -> User | None:
        """Load the user identified by a token subject."""
        ...
