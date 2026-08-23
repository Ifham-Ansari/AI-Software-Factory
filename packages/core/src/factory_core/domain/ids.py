"""Identifier generation.

Every entity identifier in the system is produced here. Centralising generation means
the scheme can change — to time-ordered UUIDv7 for index locality, for example — without
touching a single call site.

UUIDv4 is used today. Phase 1 tables are small and their access paths are indexed by
``created_at`` rather than by primary key ordering, so random keys cost nothing yet.
Revisit when the append-heavy tables (``workflow_events``, ``tasks``) arrive in Phase 2.
"""

from __future__ import annotations

import uuid
from typing import NewType

UserId = NewType("UserId", uuid.UUID)
ProjectId = NewType("ProjectId", uuid.UUID)
TokenId = NewType("TokenId", uuid.UUID)
TokenFamilyId = NewType("TokenFamilyId", uuid.UUID)
AuditEntryId = NewType("AuditEntryId", uuid.UUID)
VerificationId = NewType("VerificationId", uuid.UUID)


def new_id() -> uuid.UUID:
    """Generate a fresh entity identifier."""
    return uuid.uuid4()


def new_user_id() -> UserId:
    """Generate a fresh user identifier."""
    return UserId(new_id())


def new_project_id() -> ProjectId:
    """Generate a fresh project identifier."""
    return ProjectId(new_id())


def new_token_id() -> TokenId:
    """Generate a fresh refresh-token identifier."""
    return TokenId(new_id())


def new_token_family_id() -> TokenFamilyId:
    """Generate a fresh refresh-token family identifier."""
    return TokenFamilyId(new_id())


def new_verification_id() -> VerificationId:
    """Generate a fresh email-verification identifier."""
    return VerificationId(new_id())


def parse_uuid(value: str) -> uuid.UUID | None:
    """Parse a string as a UUID, returning ``None`` when it is not one.

    Used at trust boundaries where a caller-supplied path segment must not raise.
    """
    try:
        return uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return None
