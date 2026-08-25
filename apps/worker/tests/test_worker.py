"""Worker process lifecycle.

Start-up, refusal to start without a database, and clean shutdown. What the worker
actually *does* with a claimed job is covered in ``test_processor.py``.

``test_stops_when_asked`` is the load-bearing one: the settings here point at a database
that may not exist, so a stop request must not have to wait for a claim's connect timeout.
That is why the claim races the stop event rather than being awaited outright.
"""

from __future__ import annotations

import asyncio

import pytest

from factory_core.config import (
    ApiSettings,
    DatabaseSettings,
    Environment,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_worker.runner import Worker

pytestmark = pytest.mark.unit


@pytest.fixture
def settings() -> Settings:
    return Settings(
        environment=Environment.TEST,
        database=DatabaseSettings(url="postgresql://test:test@localhost:5432/test"),  # type: ignore[arg-type]
        security=SecuritySettings(
            jwt_secret_key="test-secret-key-that-is-at-least-32-characters",  # type: ignore[arg-type]
        ),
        observability=ObservabilitySettings(service_name="worker-test", log_level="WARNING"),
        api=ApiSettings(),
    )


class TestLifecycle:
    async def test_stops_when_asked(self, settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """A stop request must end the loop promptly, not on the next tick boundary."""

        async def no_database_check(_factory: object) -> None:
            return None

        monkeypatch.setattr(Worker, "_verify_database", staticmethod(no_database_check))
        worker = Worker(settings)

        async def stop_shortly() -> None:
            await asyncio.sleep(0.05)
            worker.request_stop()

        await asyncio.wait_for(asyncio.gather(worker.run(), stop_shortly()), timeout=5.0)

    async def test_stop_is_idempotent(self, settings: Settings) -> None:
        """Both SIGINT and SIGTERM can arrive; the second must be harmless."""
        worker = Worker(settings)

        worker.request_stop()
        worker.request_stop()

    @pytest.mark.failure
    async def test_refuses_to_start_without_a_database(self, settings: Settings) -> None:
        """A worker looping happily with no database looks healthy and does nothing.

        Points at TEST-NET-1 (RFC 5737, guaranteed unroutable) with a short
        ``connect_timeout`` so the failure is fast and deterministic. Using localhost
        would depend on whether the developer happens to have Postgres running.

        Asserted on the driver error class rather than message text, which varies by
        platform and by why the connection failed.
        """
        from sqlalchemy.exc import DBAPIError

        unreachable = settings.model_copy(
            update={
                "database": DatabaseSettings(
                    url="postgresql://t:t@192.0.2.1:5432/t?connect_timeout=2"  # type: ignore[arg-type]
                )
            }
        )
        worker = Worker(unreachable)

        with pytest.raises(DBAPIError):
            await asyncio.wait_for(worker.run(), timeout=20.0)


class TestSignalHandlers:
    async def test_install_does_not_raise(self, settings: Settings) -> None:
        """add_signal_handler is unavailable on Windows; the fallback must cover it."""
        from factory_worker.runner import install_signal_handlers

        worker = Worker(settings)

        install_signal_handlers(worker, asyncio.get_running_loop())
