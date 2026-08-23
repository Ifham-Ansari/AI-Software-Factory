"""Pagination, sorting and filtering query parameters."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query

from factory_core.domain.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    PageRequest,
    SortDirection,
)


def get_page_request(
    page: Annotated[int, Query(ge=1, description="Page number, 1-based.")] = 1,
    page_size: Annotated[
        int,
        Query(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Items per page, at most {MAX_PAGE_SIZE}.",
        ),
    ] = DEFAULT_PAGE_SIZE,
    sort_by: Annotated[
        str | None,
        Query(
            max_length=40,
            description="Field to sort by. Validated against a per-collection allowlist.",
        ),
    ] = None,
    direction: Annotated[SortDirection, Query()] = SortDirection.DESC,
) -> PageRequest:
    """Build a page request from query parameters.

    Bounds are declared here so FastAPI rejects an out-of-range page size at the edge
    with a 422, before any handler runs. An unbounded page size is a cheap way to make
    the database do unbounded work.
    """
    return PageRequest(page=page, page_size=page_size, sort_by=sort_by, direction=direction)


PageRequestDep = Annotated[PageRequest, Depends(get_page_request)]
