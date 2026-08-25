"""Dependency providers for the secret vault, events and the job queue.

Kept apart from ``services.py`` so neither file outgrows a screenful; the split is by
phase because these providers share one trait the Phase 1 ones do not — they are all
scoped to a **project** that the caller must be proven to own.

That ownership check is the important part. Every provider here resolves the project id
from the path *and then verifies it against the authenticated user's project repository*.
A provider that trusted the path parameter would let any signed-in user read any project's
secrets, so the lookup is not an optimisation to be skipped.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Path

from factory_api.dependencies.context import RequestIdDep, SessionDep, StateDep
from factory_api.dependencies.services import ProjectRepositoryDep
from factory_core.application.secrets import ConfigurationService, SecretVault
from factory_core.domain.ids import ProjectId, parse_uuid
from factory_core.errors import ConfigurationError, NotFoundError
from factory_core.events import EventPublisher, EventStore
from factory_core.infrastructure.queue import JobQueue
from factory_core.persistence.repositories.config_requirements import (
    ConfigRequirementRepository,
)
from factory_core.persistence.repositories.secrets import (
    ProjectKeyRepository,
    SecretAccessLogRepository,
    SecretRepository,
)


async def get_owned_project_id(
    projects: ProjectRepositoryDep,
    project_id: Annotated[str, Path()],
) -> ProjectId:
    """Resolve a path project id, proving the caller owns it.

    Raises:
        NotFoundError: The id is malformed, or the project does not belong to the
            authenticated user. Both report 404 rather than 403 — a 403 would confirm
            that a project with that id exists.
    """
    parsed = parse_uuid(project_id)
    if parsed is None:
        raise NotFoundError("The requested project was not found.")
    owned = ProjectId(parsed)
    if await projects.get(owned) is None:
        raise NotFoundError("The requested project was not found.")
    return owned


OwnedProjectId = Annotated[ProjectId, Depends(get_owned_project_id)]


def get_secret_vault(
    session: SessionDep, state: StateDep, project_id: OwnedProjectId
) -> SecretVault:
    """Build a vault bound to an owned project.

    Raises:
        ConfigurationError: No master key is configured, so nothing can be encrypted or
            decrypted. Refusing is the only safe answer — the alternative would be
            storing credentials in the clear.
    """
    if state.keyring is None:
        msg = (
            "The secret vault is unavailable: SECRETS__MASTER_KEY is not configured. "
            "Generate one with: uv run python scripts/generate_master_key.py"
        )
        raise ConfigurationError(msg)
    return SecretVault(
        secrets=SecretRepository(session, project_id=project_id),
        project_keys=ProjectKeyRepository(session),
        access_log=SecretAccessLogRepository(session),
        keyring=state.keyring,
    )


def get_configuration_service(
    session: SessionDep, project_id: OwnedProjectId
) -> ConfigurationService:
    """Build the configuration-requirements service for an owned project."""
    return ConfigurationService(
        requirements=ConfigRequirementRepository(session, project_id=project_id),
        secrets=SecretRepository(session, project_id=project_id),
        project_id=project_id,
    )


def get_event_store(session: SessionDep) -> EventStore:
    """Build the event store for this request's transaction."""
    return EventStore(session)


def get_event_publisher(
    store: Annotated[EventStore, Depends(get_event_store)], state: StateDep
) -> EventPublisher:
    """Build a publisher that records durably and fans out after commit."""
    return EventPublisher(store, state.event_bus)


def get_job_queue(session: SessionDep) -> JobQueue:
    """Build the job queue for this request's transaction.

    Sharing the request session is what makes enqueue-in-transaction work: a job and the
    state change that caused it commit together or not at all.
    """
    return JobQueue(session)


SecretVaultDep = Annotated[SecretVault, Depends(get_secret_vault)]
ConfigurationServiceDep = Annotated[ConfigurationService, Depends(get_configuration_service)]
EventStoreDep = Annotated[EventStore, Depends(get_event_store)]
EventPublisherDep = Annotated[EventPublisher, Depends(get_event_publisher)]
JobQueueDep = Annotated[JobQueue, Depends(get_job_queue)]
RequestIdentity = RequestIdDep
