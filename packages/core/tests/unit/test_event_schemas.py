"""Event envelope validation [F-208].

The acceptance criterion is "unknown event type rejected at the boundary". These tests
drive that from both directions: a closed enum on the way in, and payload models that
forbid extra keys so an internal object cannot leak fields onto the wire.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from factory_core.events.schemas import (
    MAX_MESSAGE_LENGTH,
    EventActor,
    EventEnvelope,
    GenericPayload,
    LogPayload,
    NewEvent,
    ProgressPayload,
    channel_for_project,
    channel_for_run,
)
from factory_core.events.types import ActorKind, EventType

pytestmark = pytest.mark.unit

RUN = uuid.uuid4()
PROJECT = uuid.uuid4()


def _envelope(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "event_id": uuid.uuid4(),
        "seq": 1,
        "type": EventType.RUN_LOG,
        "run_id": RUN,
        "project_id": PROJECT,
        "occurred_at": datetime.now(UTC),
        "actor": {"kind": ActorKind.SYSTEM, "id": None},
        "payload": {"kind": "log", "message": "hello"},
    }
    base.update(overrides)
    return base


class TestEnvelopeValidation:
    def test_a_well_formed_envelope_validates(self) -> None:
        envelope = EventEnvelope.model_validate(_envelope())

        assert envelope.seq == 1
        assert isinstance(envelope.payload, LogPayload)

    @pytest.mark.failure
    def test_unknown_event_type_is_rejected(self) -> None:
        """The acceptance criterion for F-208."""
        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(_envelope(type="totally.invented"))

    @pytest.mark.failure
    def test_extra_envelope_fields_are_rejected(self) -> None:
        """Silently accepting an unexpected field is how internal state leaks."""
        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(_envelope(internal_state={"secret": "x"}))

    @pytest.mark.failure
    @pytest.mark.parametrize("seq", [0, -1])
    def test_sequence_numbers_start_at_one(self, seq: int) -> None:
        """Zero is the "I have nothing" cursor a client sends, so no event may carry it."""
        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(_envelope(seq=seq))

    @pytest.mark.failure
    def test_unknown_payload_kind_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(_envelope(payload={"kind": "mystery"}))

    @pytest.mark.failure
    def test_oversized_message_is_rejected(self) -> None:
        """A runaway log line would otherwise be pushed to every connected socket."""
        with pytest.raises(ValidationError):
            EventEnvelope.model_validate(
                _envelope(payload={"kind": "log", "message": "x" * (MAX_MESSAGE_LENGTH + 1)})
            )

    def test_payload_discriminates_on_kind(self) -> None:
        progress = EventEnvelope.model_validate(
            _envelope(
                type=EventType.JOB_PROGRESS,
                payload={"kind": "progress", "message": "half", "fraction": 0.5},
            )
        )

        assert isinstance(progress.payload, ProgressPayload)
        assert progress.payload.fraction == 0.5

    @pytest.mark.failure
    @pytest.mark.parametrize("fraction", [-0.1, 1.1])
    def test_fraction_is_bounded(self, fraction: float) -> None:
        with pytest.raises(ValidationError):
            ProgressPayload(message="x", fraction=fraction)

    def test_json_round_trip_preserves_the_payload_type(self) -> None:
        """Envelopes cross the wire as JSON; the discriminator must survive."""
        original = EventEnvelope.model_validate(_envelope())

        restored = EventEnvelope.model_validate_json(original.model_dump_json())

        assert restored == original
        assert isinstance(restored.payload, LogPayload)


class TestNewEvent:
    def test_sequence_cannot_be_supplied_by_a_caller(self) -> None:
        """`seq` belongs to the store. A caller that could set it could create a gap."""
        with pytest.raises(ValidationError):
            NewEvent(type=EventType.RUN_LOG, run_id=RUN, project_id=PROJECT, seq=5)  # type: ignore[call-arg]

    def test_defaults_to_a_system_actor_and_generic_payload(self) -> None:
        event = NewEvent(type=EventType.RUN_LOG, run_id=RUN, project_id=PROJECT)

        assert event.actor.kind is ActorKind.SYSTEM
        assert isinstance(event.payload, GenericPayload)


class TestActors:
    def test_constructors_set_the_right_kind(self) -> None:
        user_id = uuid.uuid4()

        assert EventActor.system().kind is ActorKind.SYSTEM
        assert EventActor.user(user_id).id == str(user_id)
        assert EventActor.agent("architect").kind is ActorKind.AGENT

    def test_actor_is_immutable(self) -> None:
        """An event already published must not be mutable after the fact."""
        actor = EventActor.system()

        with pytest.raises(ValidationError):
            actor.kind = ActorKind.USER  # type: ignore[misc]


class TestChannels:
    def test_run_and_project_channels_are_distinct(self) -> None:
        assert channel_for_run(RUN) == f"events:run:{RUN}"
        assert channel_for_project(PROJECT) == f"events:project:{PROJECT}"
        assert channel_for_run(RUN) != channel_for_project(RUN)

    def test_channels_are_stable_across_string_and_uuid(self) -> None:
        assert channel_for_run(RUN) == channel_for_run(str(RUN))
