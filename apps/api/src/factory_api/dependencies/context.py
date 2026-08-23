"""Request-scoped dependency providers for infrastructure."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from factory_api.state import AppState
from factory_core.infrastructure.email import EmailSender
from factory_core.persistence import unit_of_work


def get_state(request: Request) -> AppState:
    """Return the process-wide application state."""
    state: AppState = request.app.state.app_state
    return state


def get_request_id(request: Request) -> str | None:
    """Return this request's correlation id."""
    value = getattr(request.state, "request_id", None)
    return str(value) if value else None


async def get_session(
    state: Annotated[AppState, Depends(get_state)],
) -> AsyncIterator[AsyncSession]:
    """Provide a session inside a transaction for the life of the request.

    One transaction per request. The handler never commits: the unit of work commits when
    the handler returns and rolls back if it raises, so a request cannot half-apply a
    change by returning early on one branch.
    """
    async with unit_of_work(state.session_factory) as session:
        yield session


def get_email_sender(request: Request) -> EmailSender:
    """Return the process-wide email transport.

    A dependency rather than a direct read of application state, so tests can swap in
    a recording transport through the same override mechanism as the repositories.
    """
    state: AppState = request.app.state.app_state
    return state.email_sender


StateDep = Annotated[AppState, Depends(get_state)]
EmailSenderDep = Annotated[EmailSender, Depends(get_email_sender)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RequestIdDep = Annotated[str | None, Depends(get_request_id)]
