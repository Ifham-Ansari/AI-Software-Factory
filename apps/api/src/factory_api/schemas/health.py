"""Health and readiness response bodies."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from factory_core.application.health import HealthReport


class DependencyResponse(BaseModel):
    """One dependency's state."""

    model_config = ConfigDict(extra="forbid")

    name: str
    status: str
    latency_ms: float | None = None
    detail: str | None = Field(
        default=None,
        description="Exception type when unhealthy. Never a driver message, which can "
        "contain a connection string.",
    )


class HealthResponse(BaseModel):
    """Liveness. Answers only 'is this process running', and touches nothing external."""

    model_config = ConfigDict(extra="forbid")

    status: str
    service: str
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    """Readiness. Answers 'can this process serve traffic', and probes dependencies."""

    model_config = ConfigDict(extra="forbid")

    status: str
    dependencies: list[DependencyResponse]

    @classmethod
    def from_report(cls, report: HealthReport) -> ReadinessResponse:
        """Project a health report onto its wire representation."""
        return cls(
            status=report.status.value,
            dependencies=[
                DependencyResponse(
                    name=dependency.name,
                    status=dependency.status.value,
                    latency_ms=dependency.latency_ms,
                    detail=dependency.detail,
                )
                for dependency in report.dependencies
            ],
        )
