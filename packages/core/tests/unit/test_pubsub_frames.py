"""Which pub/sub frames become events, and which do not [F-210].

A subscription carries more than published messages: subscribe and unsubscribe
confirmations arrive on the same stream, and so do the replies to redis-py's periodic
health-check ``PING``, as ``pong`` frames whose ``data`` is a string.

That last one is the reason this file exists. ``ignore_subscribe_messages=True`` does *not*
filter pongs — ``handle_message`` returns them regardless — so a payload filter that only
asked "is ``data`` a string?" would forward a keepalive to every browser watching the run.
The client would fail to parse it and carry on, which is precisely what makes the bug worth
a test: it is invisible in a browser and visible only here.

These run against a stub rather than a real Redis because the frames being classified are
the point, and a real broker makes it awkward to produce a pong on demand.
"""

from __future__ import annotations

from typing import Any

import pytest

from factory_core.infrastructure.redis.pubsub import _messages

pytestmark = pytest.mark.unit


class _EndOfScriptError(Exception):
    """Ends the scripted stream.

    A distinct exception rather than ``StopAsyncIteration``: PEP 479 turns that into a
    ``RuntimeError`` when it escapes an async generator, which would obscure the assertion.
    """


class StubPubSub:
    """Replays a scripted sequence of frames, then stops the consumer."""

    def __init__(self, frames: list[dict[str, Any] | None]) -> None:
        self._frames = list(frames)
        self.calls = 0

    async def get_message(self, **_kwargs: Any) -> dict[str, Any] | None:
        self.calls += 1
        if not self._frames:
            raise _EndOfScriptError
        return self._frames.pop(0)


async def _drain(frames: list[dict[str, Any] | None]) -> list[str]:
    """Collect everything ``_messages`` yields for a scripted stream."""
    stub = StubPubSub(frames)
    collected: list[str] = []
    try:
        async for payload in _messages(stub):  # type: ignore[arg-type]
            collected.append(payload)
    except _EndOfScriptError:
        pass
    return collected


def _message(data: str | bytes) -> dict[str, Any]:
    return {"type": "message", "channel": "events:run:1", "data": data}


class TestFrameFiltering:
    async def test_message_frames_are_yielded(self) -> None:
        assert await _drain([_message('{"seq":1}')]) == ['{"seq":1}']

    async def test_bytes_payloads_are_decoded(self) -> None:
        """``decode_responses=True`` is set, but a caller may not have set it."""
        assert await _drain([_message(b'{"seq":1}')]) == ['{"seq":1}']

    @pytest.mark.failure
    async def test_a_health_check_pong_is_not_an_event(self) -> None:
        """The regression.

        redis-py pings the subscription every ``health_check_interval`` seconds; the reply
        is a ``pong`` frame carrying a string. Forwarding it would push an unparseable
        frame to every connected browser roughly twice a minute.
        """
        frames: list[dict[str, Any] | None] = [
            {"type": "pong", "channel": None, "data": ""},
            _message('{"seq":1}'),
        ]

        assert await _drain(frames) == ['{"seq":1}']

    @pytest.mark.failure
    async def test_subscribe_confirmations_are_not_events(self) -> None:
        frames: list[dict[str, Any] | None] = [
            {"type": "subscribe", "channel": "events:run:1", "data": 1},
            {"type": "unsubscribe", "channel": "events:run:1", "data": 0},
            _message('{"seq":1}'),
        ]

        assert await _drain(frames) == ['{"seq":1}']

    async def test_an_idle_window_is_not_an_error(self) -> None:
        """``None`` means "nothing published yet", and the loop simply waits again.

        This is what the subscription used to get wrong: an idle window raised instead,
        and the subscription ended for good.
        """
        assert await _drain([None, None, _message('{"seq":1}')]) == ['{"seq":1}']
