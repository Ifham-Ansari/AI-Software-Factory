"""Health and readiness aggregation."""

from __future__ import annotations

import asyncio
import time

import pytest

from factory_core.application.health import HealthService, HealthStatus

pytestmark = pytest.mark.unit


async def _ok() -> None:
    return None


async def _fail() -> None:
    raise RuntimeError("dependency is down")


class TestAggregation:
    async def test_no_dependencies_is_healthy(self) -> None:
        report = await HealthService().check()

        assert report.status is HealthStatus.HEALTHY
        assert report.is_ready

    async def test_all_healthy(self) -> None:
        service = HealthService({"database": _ok, "cache": _ok})

        report = await service.check()

        assert report.status is HealthStatus.HEALTHY
        assert {d.name for d in report.dependencies} == {"database", "cache"}

    async def test_one_failure_makes_the_process_not_ready(self) -> None:
        service = HealthService({"database": _ok, "cache": _fail})

        report = await service.check()

        assert report.status is HealthStatus.UNHEALTHY
        assert not report.is_ready

    async def test_latency_is_recorded(self) -> None:
        report = await HealthService({"database": _ok}).check()

        assert report.dependencies[0].latency_ms is not None

    async def test_probes_run_concurrently(self) -> None:
        """Serial probes make readiness latency the sum of every dependency."""

        async def slow() -> None:
            await asyncio.sleep(0.15)

        service = HealthService({f"dep{i}": slow for i in range(4)})

        started = time.perf_counter()
        await service.check()
        elapsed = time.perf_counter() - started

        assert elapsed < 0.5, "probes appear to be running in series"


@pytest.mark.failure
class TestFailureHandling:
    async def test_check_never_raises(self) -> None:
        """The readiness endpoint must answer even when everything is broken."""
        report = await HealthService({"database": _fail}).check()

        assert report.status is HealthStatus.UNHEALTHY

    @pytest.mark.security
    async def test_only_the_exception_type_is_reported(self) -> None:
        """Driver errors routinely embed the connection string."""

        async def leaky() -> None:
            raise RuntimeError("connect failed: postgresql://user:hunter2@host/db")

        report = await HealthService({"database": leaky}).check()

        assert report.dependencies[0].detail == "RuntimeError"
        assert "hunter2" not in str(report.model_dump())

    async def test_a_hanging_probe_is_cut_short(self) -> None:
        """A readiness endpoint that hangs is worse than one that reports failure."""

        async def hangs() -> None:
            await asyncio.sleep(30)

        service = HealthService({"database": hangs}, timeout_seconds=0.1)

        started = time.perf_counter()
        report = await service.check()
        elapsed = time.perf_counter() - started

        assert elapsed < 2.0
        assert report.status is HealthStatus.UNHEALTHY
        assert report.dependencies[0].detail == "Timeout"

    async def test_one_hanging_probe_does_not_block_the_others(self) -> None:
        async def hangs() -> None:
            await asyncio.sleep(30)

        service = HealthService({"slow": hangs, "fast": _ok}, timeout_seconds=0.1)

        report = await service.check()

        fast = next(d for d in report.dependencies if d.name == "fast")
        assert fast.status is HealthStatus.HEALTHY


class TestRegistration:
    async def test_register_adds_a_probe(self) -> None:
        service = HealthService()

        service.register("database", _ok)

        assert len((await service.check()).dependencies) == 1

    async def test_register_replaces_an_existing_probe(self) -> None:
        service = HealthService({"database": _ok})

        service.register("database", _fail)

        report = await service.check()
        assert len(report.dependencies) == 1
        assert report.status is HealthStatus.UNHEALTHY
