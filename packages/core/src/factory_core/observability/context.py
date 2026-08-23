"""Correlation identifiers carried implicitly through a unit of work.

Identifiers live in context variables rather than being threaded through every call
signature. A request handler binds them once at the edge and every log line emitted
underneath — however deep — carries them automatically.

Context variables are the right tool here because asyncio tasks inherit a copy of the
context at creation, so concurrent requests cannot observe each other's identifiers.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from typing import Any

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_project_id: ContextVar[str | None] = ContextVar("project_id", default=None)

_VARS: dict[str, ContextVar[str | None]] = {
    "request_id": _request_id,
    "user_id": _user_id,
    "project_id": _project_id,
}


def new_request_id() -> str:
    """Generate a fresh request identifier."""
    return uuid.uuid4().hex


def get_request_id() -> str | None:
    """Return the current request identifier, if one is bound."""
    return _request_id.get()


def get_user_id() -> str | None:
    """Return the current authenticated user identifier, if one is bound."""
    return _user_id.get()


def get_project_id() -> str | None:
    """Return the current project identifier, if one is bound."""
    return _project_id.get()


def current_context() -> dict[str, str]:
    """Snapshot every bound identifier.

    Returns:
        Mapping of identifier name to value, omitting anything unbound.
    """
    return {name: value for name, var in _VARS.items() if (value := var.get()) is not None}


@contextmanager
def bind_context(**values: str | None) -> Iterator[None]:
    """Bind correlation identifiers for the duration of the block.

    Unknown keys are ignored rather than raising: a caller adding a future identifier
    should not crash a logging path.

    Args:
        **values: Identifier names and values. ``None`` values are skipped.
    """
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    for name, value in values.items():
        var = _VARS.get(name)
        if var is None or value is None:
            continue
        tokens.append((var, var.set(value)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)


def context_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor that merges correlation identifiers into every event."""
    for name, value in current_context().items():
        event_dict.setdefault(name, value)
    return event_dict
