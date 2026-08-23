"""Domain entities, value objects, policies and pagination."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError as PydanticValidationError

from factory_core.domain import (
    Page,
    PageRequest,
    Project,
    ProjectStatus,
    SortDirection,
    User,
    UserStatus,
    ensure_active_user,
    ensure_can_access_project,
    ensure_can_modify_project,
    normalise_email,
    parse_uuid,
    slugify,
)
from factory_core.domain.ids import UserId
from factory_core.errors import AuthorizationError, NotFoundError, ValidationError

pytestmark = pytest.mark.unit


class TestEmail:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("Ada@Example.com", "ada@example.com"),
            ("  ada@example.com  ", "ada@example.com"),
            ("ADA@EXAMPLE.COM", "ada@example.com"),
        ],
    )
    def test_normalisation(self, given: str, expected: str) -> None:
        """Case and whitespace must not create duplicate accounts."""
        assert normalise_email(given) == expected

    @pytest.mark.parametrize("bad", ["", "not-an-email", "@example.com", "a@", "a b@c.com"])
    def test_invalid_addresses_rejected(self, bad: str) -> None:
        with pytest.raises(PydanticValidationError):
            normalise_email(bad)


class TestSlugify:
    @pytest.mark.parametrize(
        ("given", "expected"),
        [
            ("Restaurant System", "restaurant-system"),
            ("  Spaces  Everywhere  ", "spaces-everywhere"),
            ("Ünïcödé Café", "unicode-cafe"),
            ("Sym!@#bols", "sym-bols"),
            ("---dashes---", "dashes"),
            ("CamelCaseName", "camelcasename"),
        ],
    )
    def test_produces_url_safe_slug(self, given: str, expected: str) -> None:
        assert slugify(given) == expected

    @pytest.mark.parametrize("empty", ["", "   ", "!!!", "🎉"])
    def test_falls_back_when_nothing_survives(self, empty: str) -> None:
        """An empty slug would produce a broken URL."""
        assert slugify(empty) == "project"

    def test_length_is_bounded(self) -> None:
        assert len(slugify("word " * 100)) <= 80

    def test_never_ends_with_a_dash(self) -> None:
        """Truncation can land mid-separator; the result must still be clean."""
        assert not slugify("a" * 79 + " bbbb").endswith("-")


class TestEntities:
    def test_user_is_immutable(self, user: User) -> None:
        with pytest.raises(PydanticValidationError):
            user.email = "other@example.com"  # type: ignore[misc]

    def test_unknown_fields_rejected(self) -> None:
        """Silently accepting stray fields hides typos and schema drift."""
        with pytest.raises(PydanticValidationError):
            User(  # type: ignore[call-arg]
                id=UserId(parse_uuid("00000000-0000-4000-8000-000000000001")),  # type: ignore[arg-type]
                email="a@b.test",
                display_name="A",
                status=UserStatus.ACTIVE,
                created_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
                updated_at="2026-01-01T00:00:00Z",  # type: ignore[arg-type]
                is_admin=True,
            )

    def test_user_entity_carries_no_password_material(self, user: User) -> None:
        """An entity that cannot hold a hash can never leak one."""
        serialised = json.dumps(user.model_dump(mode="json")).lower()

        assert "password" not in serialised
        assert "hash" not in serialised

    def test_suspended_user_cannot_authenticate(self, user: User) -> None:
        suspended = user.model_copy(update={"status": UserStatus.SUSPENDED})

        assert not suspended.is_active

    def test_archived_project_flag(self, project: Project) -> None:
        archived = project.model_copy(update={"status": ProjectStatus.ARCHIVED})

        assert archived.is_archived
        assert not project.is_archived


class TestOwnershipPolicy:
    """Project isolation is the central security boundary of the system."""

    def test_owner_may_access(self, project: Project, user_id: UserId) -> None:
        assert ensure_can_access_project(user_id, project) is project

    @pytest.mark.security
    def test_stranger_gets_not_found_not_forbidden(
        self, project: Project, other_user_id: UserId
    ) -> None:
        """403 would confirm the project exists and enable enumeration."""
        with pytest.raises(NotFoundError):
            ensure_can_access_project(other_user_id, project)

    @pytest.mark.security
    def test_missing_project_is_indistinguishable_from_forbidden(
        self, user_id: UserId, project: Project, other_user_id: UserId
    ) -> None:
        missing = pytest.raises(NotFoundError)
        with missing as absent:
            ensure_can_access_project(user_id, None)
        with pytest.raises(NotFoundError) as forbidden:
            ensure_can_access_project(other_user_id, project)

        assert absent.value.message == forbidden.value.message
        assert absent.value.code == forbidden.value.code

    def test_owner_may_modify_draft(self, project: Project, user_id: UserId) -> None:
        assert ensure_can_modify_project(user_id, project) is project

    def test_archived_project_is_read_only(self, project: Project, user_id: UserId) -> None:
        archived = project.model_copy(update={"status": ProjectStatus.ARCHIVED})

        with pytest.raises(AuthorizationError):
            ensure_can_modify_project(user_id, archived)

    @pytest.mark.security
    def test_stranger_cannot_modify(self, project: Project, other_user_id: UserId) -> None:
        with pytest.raises(NotFoundError):
            ensure_can_modify_project(other_user_id, project)

    def test_suspended_user_refused(self, user: User) -> None:
        with pytest.raises(AuthorizationError):
            ensure_active_user(user.model_copy(update={"status": UserStatus.SUSPENDED}))


class TestPagination:
    def test_offset_and_limit(self) -> None:
        request = PageRequest(page=3, page_size=20)

        assert request.offset == 40
        assert request.limit == 20

    @pytest.mark.parametrize(("page", "size"), [(0, 20), (1, 0), (1, 101), (-1, 20)])
    def test_out_of_range_rejected(self, page: int, size: int) -> None:
        """An unbounded page size is a denial-of-service vector."""
        with pytest.raises(PydanticValidationError):
            PageRequest(page=page, page_size=size)

    def test_sort_allowlist_accepts_known_field(self) -> None:
        request = PageRequest(sort_by="name")

        assert request.resolve_sort(["name", "created_at"], "created_at") == "name"

    @pytest.mark.security
    def test_sort_allowlist_rejects_unknown_field(self) -> None:
        """Unvalidated sort columns are an injection vector."""
        request = PageRequest(sort_by="password_hash; DROP TABLE users")

        with pytest.raises(ValidationError):
            request.resolve_sort(["name", "created_at"], "created_at")

    def test_sort_defaults_when_unspecified(self) -> None:
        assert PageRequest().resolve_sort(["name"], "created_at") == "created_at"

    def test_default_direction_is_newest_first(self) -> None:
        assert PageRequest().direction is SortDirection.DESC

    @pytest.mark.parametrize(
        ("total", "size", "expected"),
        [(0, 20, 1), (1, 20, 1), (20, 20, 1), (21, 20, 2), (100, 7, 15)],
    )
    def test_total_pages(self, total: int, size: int, expected: int) -> None:
        page: Page[str] = Page(items=[], total=total, page=1, page_size=size)

        assert page.total_pages == expected

    def test_navigation_flags(self) -> None:
        middle: Page[str] = Page(items=[], total=100, page=2, page_size=20)

        assert middle.has_next
        assert middle.has_previous

    def test_empty_page_matches_request(self) -> None:
        page: Page[str] = Page.empty(PageRequest(page=2, page_size=15))

        assert page.items == []
        assert page.total == 0
        assert page.page == 2
        assert page.page_size == 15


class TestParseUuid:
    def test_valid_uuid(self) -> None:
        assert parse_uuid("00000000-0000-4000-8000-000000000001") is not None

    @pytest.mark.parametrize("bad", ["", "abc", "1", "../../etc/passwd", "' OR 1=1--"])
    def test_invalid_returns_none_rather_than_raising(self, bad: str) -> None:
        """Called on caller-supplied path segments, so it must never raise."""
        assert parse_uuid(bad) is None
