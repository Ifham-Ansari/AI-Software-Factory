"""Shared response shapes."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from factory_core.domain.pagination import Page


class PageMeta(BaseModel):
    """Pagination metadata, kept separate from the items themselves.

    Clients need totals to render controls; nesting them alongside the array rather than
    inside it keeps the item schema clean.
    """

    model_config = ConfigDict(extra="forbid")

    page: int = Field(description="Current page, 1-based.")
    page_size: int = Field(description="Items per page.")
    total: int = Field(description="Total items matching the query.")
    total_pages: int = Field(description="Total pages available.")
    has_next: bool
    has_previous: bool

    @classmethod
    def from_page[T](cls, page: Page[T]) -> PageMeta:
        """Build metadata from a domain page of any item type."""
        return cls(
            page=page.page,
            page_size=page.page_size,
            total=page.total,
            total_pages=page.total_pages,
            has_next=page.has_next,
            has_previous=page.has_previous,
        )


class PaginatedResponse[T](BaseModel):
    """A page of items plus its metadata."""

    model_config = ConfigDict(extra="forbid")

    items: list[T]
    meta: PageMeta


class MessageResponse(BaseModel):
    """A bare acknowledgement, for endpoints with nothing else to return."""

    model_config = ConfigDict(extra="forbid")

    message: str
