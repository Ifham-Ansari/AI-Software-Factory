"""Single-use WebSocket tickets.

Browsers cannot set headers on a WebSocket handshake, which leaves three ways to
authenticate one, and two of them are bad:

* **Cookies** are sent automatically, which makes the handshake CSRF-prone: any origin can
  open a socket to us and the browser attaches the session.
* **A token in the query string** lands in access logs, proxy logs and browser history —
  the one place a bearer token must never be.
* **A short-lived single-use ticket**, minted over an authenticated REST call and redeemed
  once at the handshake. It is in the URL, but it is worthless seconds later and worthless
  after one use.

Tickets are held in memory rather than Redis. They live for 30 seconds and the client
redeems one immediately against the replica that issued it; replicating that state would
cost a round trip to save a retry. If a ticket reaches the wrong replica the client simply
mints another, which is why redemption failure is a normal, quiet outcome.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from factory_core.domain.ids import ProjectId, UserId

#: Long enough to survive a slow page load, short enough to be useless if it leaks.
TICKET_TTL_SECONDS = 30

#: Bounds memory if a client mints tickets it never redeems.
MAX_OUTSTANDING_TICKETS = 10_000


@dataclass(frozen=True, slots=True)
class Ticket:
    """An issued, unredeemed ticket."""

    value: str
    user_id: UserId
    project_id: ProjectId
    expires_at: datetime

    def is_expired(self, *, now: datetime | None = None) -> bool:
        """Whether this ticket may no longer be redeemed."""
        return (now or datetime.now(UTC)) >= self.expires_at


class TicketRegistry:
    """Mints and redeems WebSocket tickets.

    One instance per API process, held on application state.
    """

    def __init__(self, *, ttl_seconds: int = TICKET_TTL_SECONDS) -> None:
        self._ttl_seconds = ttl_seconds
        self._tickets: dict[str, Ticket] = {}

    def issue(self, *, user_id: UserId, project_id: ProjectId) -> Ticket:
        """Mint a ticket binding one user to one project.

        The binding is what stops a ticket for a project the caller owns from being
        replayed against a project they do not: the handshake checks both.
        """
        self._evict_expired()
        if len(self._tickets) >= MAX_OUTSTANDING_TICKETS:
            # Unredeemed tickets are worthless after 30 seconds, so dropping the oldest
            # is safe and bounded memory matters more.
            oldest = min(self._tickets.values(), key=lambda t: t.expires_at)
            self._tickets.pop(oldest.value, None)

        ticket = Ticket(
            value=secrets.token_urlsafe(32),
            user_id=user_id,
            project_id=project_id,
            expires_at=datetime.now(UTC) + timedelta(seconds=self._ttl_seconds),
        )
        self._tickets[ticket.value] = ticket
        return ticket

    def redeem(self, value: str, *, now: datetime | None = None) -> Ticket | None:
        """Consume a ticket, returning it only if it was valid.

        Removal happens before the expiry check, so a ticket cannot be redeemed twice
        even if the second attempt arrives within the TTL. Replay is the specific attack
        this defends against.
        """
        ticket = self._tickets.pop(value, None)
        if ticket is None or ticket.is_expired(now=now):
            return None
        return ticket

    @property
    def outstanding(self) -> int:
        """How many unredeemed tickets are held. For diagnostics and tests."""
        return len(self._tickets)

    def _evict_expired(self, *, now: datetime | None = None) -> None:
        """Drop expired tickets so an idle process does not accumulate them."""
        moment = now or datetime.now(UTC)
        expired = [key for key, t in self._tickets.items() if t.is_expired(now=moment)]
        for key in expired:
            del self._tickets[key]
