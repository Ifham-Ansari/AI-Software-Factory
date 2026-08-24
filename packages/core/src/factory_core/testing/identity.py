"""In-memory identity repositories for tests.

Ships inside the package rather than in a test directory so both ``packages/core`` and
``apps/api`` can import the same implementation. Two copies of a fake drift, and a drifted
fake tests the fake rather than the system.

These stand in for the SQL repositories in tests that exercise service and HTTP behaviour.
They deliberately do **not** replace integration tests: a fake proves the service logic is
right, only a real database proves the SQL is. Anything about scoping, constraints or
transactions belongs in ``tests/integration``.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from factory_core.domain.audit import AuditAction, AuditEntry, AuditRequest
from factory_core.domain.entities import User, UserStatus
from factory_core.domain.ids import (
    AuditEntryId,
    ProjectId,
    TokenFamilyId,
    TokenId,
    UserId,
    new_id,
)
from factory_core.domain.pagination import Page, PageRequest
from factory_core.errors import AlreadyExistsError
from factory_core.security.refresh import RefreshTokenRecord, RefreshTokenStatus


class FakeUserRepository:
    """In-memory user storage."""

    def __init__(self) -> None:
        self.users: dict[UserId, User] = {}
        self.hashes: dict[UserId, str] = {}

    async def get_by_id(self, user_id: UserId) -> User | None:
        """Load a user by identifier."""
        return self.users.get(user_id)

    async def get_by_email(self, email: str) -> User | None:
        """Load a user by normalised email address."""
        return next((u for u in self.users.values() if u.email == email), None)

    async def get_credentials(self, email: str) -> tuple[User, str] | None:
        """Load a user together with their password hash."""
        user = await self.get_by_email(email)
        return (user, self.hashes[user.id]) if user else None

    async def email_exists(self, email: str) -> bool:
        """Whether an account already uses this email address."""
        return await self.get_by_email(email) is not None

    async def create(
        self,
        *,
        user_id: UserId,
        email: str,
        display_name: str,
        password_hash: str,
        now: datetime | None = None,
    ) -> User:
        """Insert a new account.

        Raises:
            AlreadyExistsError: The email is taken. Mirrors the unique constraint the
                real repository relies on, so tests see the same failure.
        """
        if await self.email_exists(email):
            raise AlreadyExistsError("An account with that email address already exists.")
        timestamp = now or datetime.now(UTC)
        user = User(
            id=user_id,
            email=email,
            display_name=display_name,
            status=UserStatus.ACTIVE,
            created_at=timestamp,
            updated_at=timestamp,
        )
        self.users[user_id] = user
        self.hashes[user_id] = password_hash
        return user

    async def update_password_hash(
        self, user_id: UserId, password_hash: str, *, now: datetime | None = None
    ) -> None:
        """Replace a stored password hash."""
        if user_id in self.hashes:
            self.hashes[user_id] = password_hash

    async def mark_email_verified(
        self, user_id: UserId, *, now: datetime | None = None
    ) -> User | None:
        """Record that a user has proven ownership of their address."""
        user = self.users.get(user_id)
        if user is None:
            return None
        if user.email_verified_at is None:
            user = user.model_copy(update={"email_verified_at": now or datetime.now(UTC)})
            self.users[user_id] = user
        return user

    def verify(self, user_id: UserId) -> None:
        """Test helper: mark an account verified without going through a code."""
        user = self.users[user_id]
        self.users[user_id] = user.model_copy(update={"email_verified_at": datetime.now(UTC)})

    def suspend(self, user_id: UserId) -> None:
        """Test helper: mark an account suspended."""
        user = self.users[user_id]
        self.users[user_id] = user.model_copy(update={"status": UserStatus.SUSPENDED})


class FakeRefreshTokenRepository:
    """In-memory refresh-token storage, including family revocation."""

    def __init__(self) -> None:
        self.tokens: dict[TokenId, RefreshTokenRecord] = {}

    async def add(self, record: RefreshTokenRecord) -> None:
        """Persist a newly issued token."""
        self.tokens[record.id] = record

    async def get_by_hash(self, token_hash: str) -> RefreshTokenRecord | None:
        """Find a token by its stored digest."""
        return next((t for t in self.tokens.values() if t.token_hash == token_hash), None)

    async def mark_rotated(
        self, token_id: TokenId, *, replaced_by: TokenId, now: datetime | None = None
    ) -> None:
        """Retire a token that has been exchanged for a successor."""
        record = self.tokens.get(token_id)
        if record is None:
            return
        self.tokens[token_id] = record.model_copy(
            update={
                "status": RefreshTokenStatus.ROTATED,
                "rotated_at": now or datetime.now(UTC),
                "replaced_by_id": replaced_by,
            }
        )

    async def revoke_family(self, family_id: TokenFamilyId, *, now: datetime | None = None) -> int:
        """Revoke every token in a family."""
        return self._revoke(lambda t: t.family_id == family_id, now)

    async def revoke_token(self, token_id: TokenId, *, now: datetime | None = None) -> None:
        """Revoke a single token."""
        self._revoke(lambda t: t.id == token_id, now)

    async def revoke_all_for_user(self, user_id: UserId, *, now: datetime | None = None) -> int:
        """Revoke every active session for a user."""
        return self._revoke(lambda t: t.user_id == user_id, now)

    async def delete_expired(self, *, before: datetime) -> int:
        """Remove tokens that expired before a cutoff."""
        stale = [tid for tid, t in self.tokens.items() if t.expires_at < before]
        for tid in stale:
            del self.tokens[tid]
        return len(stale)

    def _revoke(self, matches: Callable[[RefreshTokenRecord], bool], now: datetime | None) -> int:
        """Revoke every token matching a predicate, returning how many changed."""
        timestamp = now or datetime.now(UTC)
        count = 0
        for tid, record in list(self.tokens.items()):
            if matches(record) and record.status is not RefreshTokenStatus.REVOKED:
                self.tokens[tid] = record.model_copy(
                    update={"status": RefreshTokenStatus.REVOKED, "revoked_at": timestamp}
                )
                count += 1
        return count


class FakeAuditRepository:
    """In-memory audit log."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def record(
        self,
        request: AuditRequest,
        *,
        request_id: str | None = None,
        now: datetime | None = None,
    ) -> AuditEntry:
        """Append one audit entry."""
        entry = AuditEntry(
            id=AuditEntryId(new_id()),
            actor_type=request.actor_type,
            actor_id=request.actor_id,
            action=request.action,
            resource_type=request.resource_type,
            resource_id=request.resource_id,
            project_id=request.project_id,
            request_id=request_id,
            metadata=request.metadata,
            created_at=now or datetime.now(UTC),
        )
        self.entries.append(entry)
        return entry

    async def get(self, entry_id: AuditEntryId) -> AuditEntry | None:
        """Load one audit entry."""
        return next((e for e in self.entries if e.id == entry_id), None)

    async def list_for_actor(self, actor_id: str, request: PageRequest) -> Page[AuditEntry]:
        """List entries attributed to one actor."""
        return self._page([e for e in self.entries if e.actor_id == actor_id], request)

    async def list_for_project(
        self, project_id: ProjectId, request: PageRequest
    ) -> Page[AuditEntry]:
        """List entries for one project."""
        return self._page([e for e in self.entries if e.project_id == project_id], request)

    async def count_by_action(self, action: AuditAction, *, actor_id: str | None = None) -> int:
        """Count entries for an action."""
        return sum(
            1
            for e in self.entries
            if e.action is action and (actor_id is None or e.actor_id == actor_id)
        )

    def actions(self) -> list[AuditAction]:
        """Test helper: every recorded action, in order."""
        return [entry.action for entry in self.entries]

    @staticmethod
    def _page(items: list[AuditEntry], request: PageRequest) -> Page[AuditEntry]:
        ordered = sorted(items, key=lambda e: e.created_at, reverse=True)
        window = ordered[request.offset : request.offset + request.limit]
        return Page(
            items=window,
            total=len(ordered),
            page=request.page,
            page_size=request.page_size,
        )
