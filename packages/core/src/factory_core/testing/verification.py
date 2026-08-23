"""In-memory verification storage and a recording email transport, for tests."""

from __future__ import annotations

from datetime import UTC, datetime

from factory_core.domain.ids import UserId, VerificationId
from factory_core.infrastructure.email.messages import EmailMessage
from factory_core.security.verification import VerificationCode, VerificationStatus


class FakeVerificationRepository:
    """In-memory verification-code storage."""

    def __init__(self) -> None:
        self.codes: dict[VerificationId, VerificationCode] = {}

    async def add(self, record: VerificationCode) -> None:
        """Persist a newly issued code."""
        self.codes[record.id] = record

    async def latest_for_user(self, user_id: UserId) -> VerificationCode | None:
        """Return the most recently issued code for a user."""
        owned = [c for c in self.codes.values() if c.user_id == user_id]
        return max(owned, key=lambda c: c.issued_at) if owned else None

    async def count_issued_since(self, user_id: UserId, *, since: datetime) -> int:
        """Count codes issued to a user since a cutoff."""
        return sum(
            1 for c in self.codes.values() if c.user_id == user_id and c.issued_at >= since
        )

    async def record_attempt(self, verification_id: VerificationId) -> int:
        """Increment the attempt counter, returning the new count."""
        record = self.codes[verification_id]
        updated = record.model_copy(update={"attempts": record.attempts + 1})
        self.codes[verification_id] = updated
        return updated.attempts

    async def mark(
        self,
        verification_id: VerificationId,
        status: VerificationStatus,
        *,
        now: datetime | None = None,
    ) -> None:
        """Move a code to a terminal state."""
        record = self.codes.get(verification_id)
        if record is None:
            return
        changes: dict[str, object] = {"status": status}
        if status is VerificationStatus.CONSUMED:
            changes["consumed_at"] = now or datetime.now(UTC)
        self.codes[verification_id] = record.model_copy(update=changes)

    async def invalidate_pending(self, user_id: UserId) -> int:
        """Retire every pending code for a user."""
        count = 0
        for key, record in list(self.codes.items()):
            if record.user_id == user_id and record.status is VerificationStatus.PENDING:
                self.codes[key] = record.model_copy(
                    update={"status": VerificationStatus.EXPIRED}
                )
                count += 1
        return count

    async def delete_expired(self, *, before: datetime) -> int:
        """Remove codes that expired before a cutoff."""
        stale = [k for k, c in self.codes.items() if c.expires_at < before]
        for key in stale:
            del self.codes[key]
        return len(stale)


class RecordingEmailSender:
    """Captures messages instead of sending them.

    Tests read the code out of ``sent`` — which is the only way to obtain it, because the
    service never returns or logs a code by design.
    """

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail_next = False

    async def send(self, message: EmailMessage) -> None:
        """Record a message, or simulate a delivery failure."""
        if self.fail_next:
            self.fail_next = False
            from factory_core.errors import ServiceUnavailableError

            raise ServiceUnavailableError("Simulated delivery failure.")
        self.sent.append(message)

    def last_code(self, length: int = 6) -> str:
        """Extract the code from the most recent message."""
        import re

        if not self.sent:
            msg = "No email has been sent"
            raise AssertionError(msg)
        match = re.search(rf"\b(\d{{{length}}})\b", self.sent[-1].text_body)
        if match is None:
            msg = "No code found in the most recent email"
            raise AssertionError(msg)
        return match.group(1)
