"""The event envelope and its payloads.

Every event that reaches a browser is one of these, validated on the way in and on the way
out. Two rules make that worth the ceremony:

* **Internal objects are never serialised to a client.** A payload is a declared model
  with declared fields, so adding an attribute to a domain entity cannot silently start
  publishing it.
* **Unknown types are rejected at the boundary.** ``EventType`` is closed and payload
  models forbid extra keys, so a malformed or unrecognised event fails validation rather
  than being stored for a client to choke on later.

Payloads are kept deliberately thin — identifiers and short human-readable strings. An
event is a notification that something happened, not a transport for the thing itself; a
client that needs detail fetches it over REST, where authorization is enforced per field.

The union is discriminated on the envelope's ``type`` rather than a nested tag, matching
architecture.md §10.1. Phase 2 defines the two payload shapes it can actually emit; later
phases add their own without changing the envelope.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from factory_core.events.types import ActorKind, EventType

#: Payload text is bounded so a runaway log line cannot bloat every connected socket.
MAX_MESSAGE_LENGTH = 2_000


class EventActor(BaseModel):
    """Who or what caused an event."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: ActorKind
    #: User id, agent role, or ``None`` for the platform itself.
    id: str | None = Field(default=None, max_length=64)

    @classmethod
    def system(cls) -> EventActor:
        """The platform acting on its own behalf."""
        return cls(kind=ActorKind.SYSTEM)

    @classmethod
    def user(cls, user_id: uuid.UUID | str) -> EventActor:
        """A signed-in person."""
        return cls(kind=ActorKind.USER, id=str(user_id))

    @classmethod
    def agent(cls, role: str) -> EventActor:
        """An agent, identified by its role rather than an instance id."""
        return cls(kind=ActorKind.AGENT, id=role)


class LogPayload(BaseModel):
    """A human-readable line of run output."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["log"] = "log"
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)
    level: Literal["debug", "info", "warning", "error"] = "info"


class ProgressPayload(BaseModel):
    """Progress of a long-running unit of work."""

    model_config = ConfigDict(extra="forbid")

    kind: Literal["progress"] = "progress"
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)
    #: Completion in the range 0.0-1.0 when the total is knowable, else ``None``.
    fraction: float | None = Field(default=None, ge=0.0, le=1.0)
    job_id: uuid.UUID | None = None


class GenericPayload(BaseModel):
    """Structured detail for event types whose dedicated payload is a later phase.

    Deliberately permissive on *contents* but not on *size* or *shape*: a mapping of
    JSON-safe values, nothing else. This is what stops the catalog's Phase 4-7 members
    from being unusable until their phase arrives, without letting arbitrary Python
    objects reach the wire.
    """

    model_config = ConfigDict(extra="forbid")

    kind: Literal["generic"] = "generic"
    message: str = Field(default="", max_length=MAX_MESSAGE_LENGTH)
    data: dict[str, Any] = Field(default_factory=dict)


EventPayload = LogPayload | ProgressPayload | GenericPayload


class EventEnvelope(BaseModel):
    """A durable, ordered event belonging to exactly one run.

    ``seq`` is assigned by the event store, is dense within a run, and is the cursor a
    reconnecting client replays from. It is never set by a caller — see
    :class:`factory_core.events.store.EventStore`.
    """

    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    seq: int = Field(ge=1)
    type: EventType
    run_id: uuid.UUID
    project_id: uuid.UUID
    occurred_at: datetime
    actor: EventActor
    payload: EventPayload = Field(discriminator="kind")


class NewEvent(BaseModel):
    """An event before the store has assigned it a sequence number.

    Separate from :class:`EventEnvelope` so that ``seq`` can be non-optional there. A
    caller physically cannot construct an envelope with a made-up sequence number and
    hand it to the publisher.
    """

    model_config = ConfigDict(extra="forbid")

    type: EventType
    run_id: uuid.UUID
    project_id: uuid.UUID
    actor: EventActor = Field(default_factory=EventActor.system)
    payload: EventPayload = Field(default_factory=GenericPayload, discriminator="kind")
    occurred_at: datetime | None = None


def channel_for_run(run_id: uuid.UUID | str) -> str:
    """Redis pub/sub channel carrying one run's events.

    One channel per run rather than per project: a browser watching a run should not
    receive — and does not have to filter out — every other run's traffic.
    """
    return f"events:run:{run_id}"


def channel_for_project(project_id: uuid.UUID | str) -> str:
    """Redis pub/sub channel carrying every event for a project."""
    return f"events:project:{project_id}"
