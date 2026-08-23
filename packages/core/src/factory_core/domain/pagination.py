"""Pagination, sorting and filtering primitives.

Offset pagination is used deliberately: the collections it serves (a user's projects) are
small and benefit from jumping to an arbitrary page. The append-heavy collections that
would suffer from deep offsets — events, tasks — arrive in Phase 2 and will use
sequence-cursor pagination instead.

Sort fields are validated against an allowlist supplied by each repository rather than
being interpolated into SQL. An unvalidated sort column is an injection vector.
"""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from factory_core.errors import ValidationError

MAX_PAGE_SIZE = 100
DEFAULT_PAGE_SIZE = 20


class SortDirection(StrEnum):
    """Sort direction."""

    ASC = "asc"
    DESC = "desc"


class PageRequest(BaseModel):
    """A request for one page of a collection."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE)
    sort_by: str | None = None
    direction: SortDirection = SortDirection.DESC

    @property
    def offset(self) -> int:
        """Zero-based row offset for this page."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Maximum rows to return."""
        return self.page_size

    def resolve_sort(self, allowed: Sequence[str], default: str) -> str:
        """Validate the requested sort field against an allowlist.

        Args:
            allowed: Sortable field names for the target collection.
            default: Field to use when none was requested.

        Returns:
            A field name guaranteed to be in ``allowed``.

        Raises:
            ValidationError: The requested field is not sortable.
        """
        if self.sort_by is None:
            return default
        if self.sort_by not in allowed:
            raise ValidationError(
                f"Cannot sort by {self.sort_by!r}.",
                details={"allowed": list(allowed)},
            )
        return self.sort_by


class Page[T](BaseModel):
    """One page of results plus the totals needed to render pagination controls."""

    model_config = ConfigDict(frozen=True)

    items: list[T]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)

    @property
    def total_pages(self) -> int:
        """Total number of pages, at least 1 even when empty."""
        if self.page_size <= 0:
            return 1
        return max(1, -(-self.total // self.page_size))

    @property
    def has_next(self) -> bool:
        """Whether a following page exists."""
        return self.page < self.total_pages

    @property
    def has_previous(self) -> bool:
        """Whether a preceding page exists."""
        return self.page > 1

    @classmethod
    def empty(cls, request: PageRequest) -> Page[T]:
        """Build an empty page matching a request."""
        return cls(items=[], total=0, page=request.page, page_size=request.page_size)
