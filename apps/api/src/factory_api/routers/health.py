"""Health and readiness endpoints.

Both are unauthenticated because orchestrators probe them before any credential exists.
That makes what they return part of the public attack surface, so neither reveals
anything about configuration or dependency internals beyond up/down and a latency.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from factory_api import __version__
from factory_api.dependencies import StateDep
from factory_api.schemas import HealthResponse, ReadinessResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse, summary="Liveness")
async def health(state: StateDep) -> HealthResponse:
    """Report that this process is running.

    Touches nothing external. A failure here means the process itself is broken and
    should be restarted — which is exactly why it must not probe the database. An
    orchestrator that restarts pods because Postgres blipped turns a brief database
    problem into a full outage.
    """
    return HealthResponse(
        status="ok",
        service=state.settings.observability.service_name,
        version=__version__,
        environment=state.settings.environment.value,
    )


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness",
    responses={503: {"model": ReadinessResponse}},
)
async def ready(state: StateDep, response: Response) -> ReadinessResponse:
    """Report whether this process can serve traffic.

    Returns 503 with a per-dependency breakdown when something it depends on is down, so
    the load balancer stops routing here while the process stays up.
    """
    report = await state.health.check()
    if not report.is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse.from_report(report)
