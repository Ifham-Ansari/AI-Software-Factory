"""Health and readiness checks.

Liveness and readiness answer different questions and must not be conflated:

* **Liveness** — is this process working? It touches nothing external. If it fails, the
  right response is to restart the process.
* **Readiness** — can this process serve traffic? It probes dependencies. If it fails, the
  right response is to stop routing requests here until it recovers. Restarting would not
  help, because the problem is elsewhere.

An orchestrator that restarts pods because the database is briefly unreachable turns a
database blip into a full outage. That is why these are separate.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

from factory_core.observability import get_logger

logger = get_logger(__name__)

DEPENDENCY_TIMEOUT_SECONDS = 5.0


class HealthStatus(StrEnum):
    """Outcome of a health check."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class DependencyHealth(BaseModel):
    """The state of one dependency."""

    model_config = ConfigDict(frozen=True)

    name: str
    status: HealthStatus
    latency_ms: float | None = None
    # Never carries a driver message: those routinely contain connection strings.
    detail: str | None = None


class HealthReport(BaseModel):
    """Aggregate readiness across every dependency."""

    model_config = ConfigDict(frozen=True)

    status: HealthStatus
    dependencies: list[DependencyHealth] = Field(default_factory=list)

    @property
    def is_ready(self) -> bool:
        """Whether this process should receive traffic."""
        return self.status is not HealthStatus.UNHEALTHY


DependencyProbe = Callable[[], Awaitable[None]]


class HealthService:
    """Runs dependency probes and aggregates the result."""

    def __init__(
        self,
        probes: dict[str, DependencyProbe] | None = None,
        *,
        timeout_seconds: float = DEPENDENCY_TIMEOUT_SECONDS,
    ) -> None:
        self._probes = probes or {}
        self._timeout_seconds = timeout_seconds

    def register(self, name: str, probe: DependencyProbe) -> None:
        """Add a dependency probe.

        Args:
            name: Dependency name as it appears in the report.
            probe: Coroutine that returns normally when healthy and raises otherwise.
        """
        self._probes[name] = probe

    async def check(self) -> HealthReport:
        """Probe every dependency.

        Probes run concurrently: readiness is checked on every orchestrator poll, and
        running N probes in series makes the endpoint's latency the sum of the slowest
        path through every dependency.

        A probe that raises marks its dependency unhealthy rather than propagating. The
        readiness endpoint must always answer, even when everything underneath is broken.
        """
        results = await asyncio.gather(
            *(self._probe(name, probe) for name, probe in self._probes.items())
        )
        unhealthy = any(d.status is HealthStatus.UNHEALTHY for d in results)
        return HealthReport(
            status=HealthStatus.UNHEALTHY if unhealthy else HealthStatus.HEALTHY,
            dependencies=list(results),
        )

    async def _probe(self, name: str, probe: DependencyProbe) -> DependencyHealth:
        """Run one probe under a hard timeout.

        The timeout is the point of this method. A TCP connection to an unreachable host
        can hang for minutes, and a readiness endpoint that hangs is worse than one that
        reports failure: the orchestrator's own timeout fires, the probe is recorded as a
        failure anyway, and nobody learns which dependency was at fault.

        It bounds when the probe is *abandoned*, not total wall time. Cancelling an
        in-flight query asks the driver to cancel server-side, and that cancellation can
        itself block — so a probe may return somewhat later than the timeout. The reported
        ``latency_ms`` is the real elapsed time, not the timeout value, which is what makes
        that visible rather than mysterious.
        """
        started = time.perf_counter()
        try:
            async with asyncio.timeout(self._timeout_seconds):
                await probe()
        except TimeoutError:
            logger.warning(
                "health.dependency_timeout", dependency=name, timeout=self._timeout_seconds
            )
            return self._unhealthy(name, started, "Timeout")
        except Exception as exc:
            # The exception *type* is safe to report; its message is not, because driver
            # errors routinely embed the connection string.
            logger.warning("health.dependency_failed", dependency=name, error=type(exc).__name__)
            return self._unhealthy(name, started, type(exc).__name__)
        return DependencyHealth(
            name=name,
            status=HealthStatus.HEALTHY,
            latency_ms=_elapsed_ms(started),
        )

    @staticmethod
    def _unhealthy(name: str, started: float, detail: str) -> DependencyHealth:
        return DependencyHealth(
            name=name,
            status=HealthStatus.UNHEALTHY,
            latency_ms=_elapsed_ms(started),
            detail=detail,
        )


def _elapsed_ms(started: float) -> float:
    """Milliseconds since a ``perf_counter`` reading."""
    return round((time.perf_counter() - started) * 1000, 2)
