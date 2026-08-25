"""Secret vault and project configuration endpoints.

**No route here returns a secret value.** Storing one is a write; reading one is not
offered. That is enforced structurally rather than by discipline — the response models in
``schemas/secrets.py`` have no field a value could occupy — and
``test_secrets_api.py::TestWriteOnly`` asserts it against every route in this file.

Resolution to plaintext happens only at the three sinks in
``factory_core.security.references.SecretSink``, all of which are server-side. None is
reachable over HTTP, by design.

Every route is scoped through ``OwnedProjectId``, which verifies ownership against the
caller's own project repository before the handler runs.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import SecretStr

from factory_api.dependencies.phase2 import (
    ConfigurationServiceDep,
    OwnedProjectId,
    SecretVaultDep,
)
from factory_api.schemas.errors import ErrorResponse
from factory_api.schemas.secrets import (
    AddRequirementRequest,
    ConfigurationResponse,
    SecretListResponse,
    SecretResponse,
    StoreSecretRequest,
)
from factory_core.application.secrets.schemas import StoreSecretCommand
from factory_core.errors import NotFoundError, ValidationError

router = APIRouter(prefix="/projects/{project_id}", tags=["secrets"])

_ERRORS: dict[int | str, dict[str, object]] = {
    401: {"model": ErrorResponse},
    404: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    503: {"model": ErrorResponse},
}


@router.get(
    "/secrets",
    response_model=SecretListResponse,
    responses=_ERRORS,
    summary="List a project's secrets (metadata only)",
)
async def list_secrets(vault: SecretVaultDep) -> SecretListResponse:
    """Return every secret's metadata.

    Names, descriptions and timestamps. Never values — there is no endpoint that returns
    one, and no response model with a field for one.
    """
    views = await vault.list_secrets()
    items = [SecretResponse.from_view(view) for view in views]
    return SecretListResponse(items=items, total=len(items))


@router.put(
    "/secrets/{name}",
    response_model=SecretResponse,
    responses=_ERRORS,
    summary="Store or replace a secret value",
)
async def store_secret(
    name: str, body: StoreSecretRequest, vault: SecretVaultDep
) -> SecretResponse:
    """Encrypt and store a value.

    Idempotent by name: storing again replaces the value and bumps its version, so an
    operator rotating a credential does not have to delete first.

    Raises:
        ValidationError: The path name and body name disagree. Guessing which one was
            meant would silently write to the wrong key.
    """
    if name != body.name:
        raise ValidationError("The secret name in the path and body must match.")
    view = await vault.store(
        StoreSecretCommand(
            name=body.name,
            value=SecretStr(body.value),
            description=body.description,
        )
    )
    return SecretResponse.from_view(view)


@router.get(
    "/secrets/{name}",
    response_model=SecretResponse,
    responses=_ERRORS,
    summary="Describe one secret (metadata only)",
)
async def describe_secret(name: str, vault: SecretVaultDep) -> SecretResponse:
    """Return one secret's metadata.

    Raises:
        NotFoundError: No secret by that name in this project.
    """
    return SecretResponse.from_view(await vault.describe(name))


@router.delete(
    "/secrets/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=_ERRORS,
    summary="Delete a secret",
)
async def delete_secret(name: str, vault: SecretVaultDep) -> None:
    """Remove a secret.

    Raises:
        NotFoundError: No secret by that name, so nothing was deleted. Reported rather
            than silently succeeding, because "delete succeeded" on a typo'd name would
            leave an operator believing a credential was revoked when it was not.
    """
    if not await vault.delete(name):
        raise NotFoundError("The requested secret was not found.")


@router.get(
    "/configuration",
    response_model=ConfigurationResponse,
    responses=_ERRORS,
    summary="What this project still needs before it can be built",
)
async def get_configuration(configuration: ConfigurationServiceDep) -> ConfigurationResponse:
    """Report every requirement and whether it is satisfied.

    Satisfaction for a secret-backed requirement is derived from whether the secret
    exists, so this cannot claim a credential is present when it is not.
    """
    return ConfigurationResponse.from_report(await configuration.report())


@router.post(
    "/configuration/requirements",
    response_model=ConfigurationResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Record that this project needs a configuration entry",
)
async def add_requirement(
    body: AddRequirementRequest,
    configuration: ConfigurationServiceDep,
    _project_id: OwnedProjectId,
) -> ConfigurationResponse:
    """Add a catalog requirement to this project.

    Raises:
        ValidationError: The key is not in the catalog. Rejected here rather than ignored
            because a human typing a key deserves to be told; the intake agent in Phase 3
            uses the service directly, which drops unknown keys instead.
    """
    if not await configuration.require(body.key, required=body.required):
        raise ValidationError(f"Unknown configuration requirement: {body.key}")
    return ConfigurationResponse.from_report(await configuration.report())
