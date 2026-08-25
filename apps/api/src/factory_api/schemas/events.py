"""Event replay, WebSocket ticket, and job request/response bodies."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from factory_core.events.schemas import EventEnvelope
from factory_core.infrastructure.queue.schemas import JobStatus


class EventResponse(BaseModel):
    """One event, as delivered over REST replay and over the socket.

    The same shape on both paths on purpose: a client that can render a replayed event
    can render a live one with no branching, which is what makes reconnection seamless.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    seq: int
    type: str
    run_id: uuid.UUID
    project_id: uuid.UUID
    occurred_at: datetime
    actor_kind: str
    actor_id: str | None
    payload: dict[str, Any]

    @classmethod
    def from_envelope(cls, envelope: EventEnvelope) -> EventResponse:
        """Project a domain envelope onto the wire representation."""
        return cls(
            event_id=envelope.event_id,
            seq=envelope.seq,
            type=envelope.type.value,
            run_id=envelope.run_id,
            project_id=envelope.project_id,
            occurred_at=envelope.occurred_at,
            actor_kind=envelope.actor.kind.value,
            actor_id=envelope.actor.id,
            payload=envelope.payload.model_dump(mode="json"),
        )


class EventPageResponse(BaseModel):
    """A replay page.

    ``next_seq`` is the cursor to send on the following request, and ``has_more`` says
    whether one is needed. Returning both means the client never has to infer whether a
    short page meant "caught up" or "hit the limit".
    """

    model_config = ConfigDict(extra="forbid")

    items: list[EventResponse]
    next_seq: int
    has_more: bool
    latest_seq: int


class WebSocketTicketResponse(BaseModel):
    """A single-use ticket for opening a run's event socket."""

    model_config = ConfigDict(extra="forbid")

    ticket: str
    expires_in: int = Field(description="Seconds until the ticket can no longer be redeemed.")
    #: Relative path, so the client does not have to know the API's public origin.
    socket_path: str


class RunResponse(BaseModel):
    """A workflow run."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    project_id: uuid.UUID
    status: str
    last_seq: int
    created_at: datetime


class EnqueueJobRequest(BaseModel):
    """Submit background work.

    Phase 2 accepts only ``noop``: the pipeline is real, the work is not. Restricting the
    type at the boundary means the endpoint cannot be used to invoke handlers that later
    phases register with different privileges.
    """

    model_config = ConfigDict(extra="forbid")

    type: str = Field(default="noop", pattern=r"^noop$")
    #: How many progress events the noop handler emits. Bounded so a caller cannot use
    #: this endpoint to flood the event stream.
    steps: int = Field(default=3, ge=1, le=10)
    idempotency_key: str | None = Field(default=None, max_length=128)


class JobResponse(BaseModel):
    """An enqueued job."""

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    run_id: uuid.UUID
    type: str
    status: JobStatus
    attempts: int
