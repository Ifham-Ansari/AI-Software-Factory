"""Event loop selection.

psycopg's async mode cannot use Windows' default ProactorEventLoop. This is a regression
guard: the failure it prevents looks like a connectivity problem, so it is expensive to
diagnose and easy to reintroduce by "simplifying" the entrypoints.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from factory_core.runtime import configure_event_loop, event_loop_factory

pytestmark = pytest.mark.unit


class TestEventLoopFactory:
    def test_windows_gets_a_selector_loop(self) -> None:
        factory = event_loop_factory()

        if sys.platform == "win32":
            assert factory is asyncio.SelectorEventLoop
        else:
            # None means "the platform default is already correct", and is accepted
            # directly by asyncio.run(loop_factory=...).
            assert factory is None

    def test_the_produced_loop_is_usable(self) -> None:
        factory = event_loop_factory()
        if factory is None:
            pytest.skip("Platform default loop is already correct")

        loop = factory()
        try:
            assert "Proactor" not in type(loop).__name__
        finally:
            loop.close()

    def test_factory_result_is_accepted_by_asyncio_run(self) -> None:
        """The whole point: it can be passed straight through."""

        async def work() -> str:
            return "ok"

        assert asyncio.run(work(), loop_factory=event_loop_factory()) == "ok"


class TestConfigureEventLoop:
    def test_is_idempotent(self) -> None:
        configure_event_loop()
        configure_event_loop()

    def test_selects_a_compatible_policy(self) -> None:
        configure_event_loop()

        loop = asyncio.new_event_loop()
        try:
            assert "Proactor" not in type(loop).__name__
        finally:
            loop.close()
