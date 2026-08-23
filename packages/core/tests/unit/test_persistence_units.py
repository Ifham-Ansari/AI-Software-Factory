"""Persistence logic that needs no database.

Row-to-entity mapping and constraint-error translation are pure functions. They are the
parts of the persistence layer most worth unit-testing, because a mistake in either is
silent: a mapper that leaks a password hash, or a translation that turns a duplicate email
into a generic 409, both look fine until someone reads the output closely.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from factory_core.domain.audit import ActorType, AuditAction, ResourceType
from factory_core.domain.entities import ProjectStatus, UserStatus
from factory_core.domain.ids import new_id
from factory_core.errors import AlreadyExistsError
from factory_core.persistence.mappers import (
    to_audit_entry,
    to_project,
    to_refresh_token,
    to_refresh_token_row,
    to_user,
)
from factory_core.persistence.models import AuditLogRow, ProjectRow, RefreshTokenRow, UserRow
from factory_core.persistence.repositories.base import Repository, ScopedRepository
from factory_core.persistence.session import _translate_integrity_error
from factory_core.security.refresh import RefreshTokenStatus, generate_refresh_token

pytestmark = pytest.mark.unit

NOW = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)


class TestUserMapping:
    @staticmethod
    def _row() -> UserRow:
        return UserRow(
            id=new_id(),
            email="ada@example.com",
            display_name="Ada Lovelace",
            password_hash="$argon2id$v=19$m=19456$secret-hash-material",
            status="active",
            created_at=NOW,
            updated_at=NOW,
        )

    def test_maps_fields(self) -> None:
        user = to_user(self._row())

        assert user.email == "ada@example.com"
        assert user.status is UserStatus.ACTIVE

    @pytest.mark.security
    def test_password_hash_has_no_path_into_the_entity(self) -> None:
        """The mapper is the enforcement point: there is simply no field to copy it into."""
        user = to_user(self._row())

        serialised = json.dumps(user.model_dump(mode="json"))
        assert "argon2" not in serialised
        assert "secret-hash-material" not in serialised


class TestProjectMapping:
    def test_maps_fields(self) -> None:
        row = ProjectRow(
            id=new_id(),
            owner_id=new_id(),
            name="Restaurant System",
            slug="restaurant-system",
            description="POS.",
            status="draft",
            archived_at=None,
            created_at=NOW,
            updated_at=NOW,
        )

        project = to_project(row)

        assert project.slug == "restaurant-system"
        assert project.status is ProjectStatus.DRAFT
        assert project.archived_at is None

    def test_maps_an_archived_project(self) -> None:
        row = ProjectRow(
            id=new_id(),
            owner_id=new_id(),
            name="Old",
            slug="old",
            description="",
            status="archived",
            archived_at=NOW,
            created_at=NOW,
            updated_at=NOW,
        )

        project = to_project(row)

        assert project.is_archived
        assert project.archived_at == NOW


class TestRefreshTokenMapping:
    def test_round_trips_through_a_row(self) -> None:
        from factory_core.domain.ids import UserId, new_token_family_id, new_token_id

        issued = generate_refresh_token(
            user_id=UserId(new_id()),
            family_id=new_token_family_id(),
            token_id=new_token_id(),
            ttl_seconds=3600,
            now=NOW,
        )

        restored = to_refresh_token(to_refresh_token_row(issued.record))

        assert restored == issued.record

    def test_maps_a_rotated_token(self) -> None:
        row = RefreshTokenRow(
            id=new_id(),
            family_id=new_id(),
            user_id=new_id(),
            token_hash="a" * 64,
            status="rotated",
            issued_at=NOW,
            expires_at=NOW + timedelta(hours=1),
            rotated_at=NOW,
            revoked_at=None,
            replaced_by_id=new_id(),
        )

        record = to_refresh_token(row)

        assert record.status is RefreshTokenStatus.ROTATED
        assert record.replaced_by_id is not None
        assert not record.is_usable(now=NOW)


class TestAuditMapping:
    def test_maps_a_full_entry(self) -> None:
        row = AuditLogRow(
            id=new_id(),
            actor_type="user",
            actor_id="actor-1",
            action="project.created",
            resource_type="project",
            resource_id="resource-1",
            project_id=new_id(),
            request_id="req-1",
            audit_metadata={"name": "Mine"},
            created_at=NOW,
        )

        entry = to_audit_entry(row)

        assert entry.actor_type is ActorType.USER
        assert entry.action is AuditAction.PROJECT_CREATED
        assert entry.resource_type is ResourceType.PROJECT
        assert entry.metadata == {"name": "Mine"}

    def test_maps_a_system_entry_with_no_resource(self) -> None:
        row = AuditLogRow(
            id=new_id(),
            actor_type="system",
            actor_id=None,
            action="token.reuse_detected",
            resource_type=None,
            resource_id=None,
            project_id=None,
            request_id=None,
            audit_metadata={},
            created_at=NOW,
        )

        entry = to_audit_entry(row)

        assert entry.actor_type is ActorType.SYSTEM
        assert entry.resource_type is None
        assert entry.project_id is None


class TestConstraintTranslation:
    """Callers above persistence must not need to import SQLAlchemy to handle these."""

    @staticmethod
    def _error(constraint: str | None):  # type: ignore[no-untyped-def]
        from sqlalchemy.exc import IntegrityError

        class Diagnostic:
            constraint_name = constraint

        class OriginalError(Exception):
            diag = Diagnostic()

        return IntegrityError("stmt", {}, OriginalError())

    @pytest.mark.parametrize(
        ("constraint", "expected"),
        [
            ("uq_users_email", "email address already exists"),
            ("uq_projects_owner_id_slug", "project with that name"),
            ("uq_refresh_tokens_token_hash", "already been issued"),
        ],
    )
    def test_named_constraints_get_specific_messages(self, constraint: str, expected: str) -> None:
        # Matched on constraint *name* rather than driver message text, because names are
        # stable and messages are not.
        translated = _translate_integrity_error(self._error(constraint))

        assert isinstance(translated, AlreadyExistsError)
        assert expected in translated.message

    def test_unknown_constraint_falls_back_safely(self) -> None:
        translated = _translate_integrity_error(self._error("uq_something_new"))

        assert isinstance(translated, AlreadyExistsError)

    def test_missing_diagnostics_do_not_crash(self) -> None:
        """Not every driver populates diagnostics; translation must still return."""
        translated = _translate_integrity_error(self._error(None))

        assert isinstance(translated, AlreadyExistsError)


@pytest.mark.security
class TestRepositoryScoping:
    """An unscoped repository over project-owned data is a data leak."""

    def test_scoped_repository_requires_an_owner(self) -> None:
        with pytest.raises(ValueError, match="owner_id"):
            ScopedRepository(None, owner_id=None)  # type: ignore[arg-type]

    def test_scoped_repository_exposes_its_owner(self) -> None:
        from factory_core.domain.ids import UserId

        owner = UserId(new_id())

        assert ScopedRepository(None, owner_id=owner).owner_id == owner  # type: ignore[arg-type]

    def test_plain_repository_exposes_its_session(self) -> None:
        sentinel = object()

        assert Repository(sentinel).session is sentinel  # type: ignore[arg-type]
