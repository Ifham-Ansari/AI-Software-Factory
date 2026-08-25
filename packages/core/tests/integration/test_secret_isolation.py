"""Vault isolation and the secret access log [F-203, F-204].

Split from ``test_secret_vault.py`` (which covers storing and resolving) because these are
the security properties, and they are the ones worth finding quickly when reviewing.

Two acceptance criteria live here: one project cannot read another's secrets, and every
resolution — granted **or refused** — writes an attributable audit row.
"""

from __future__ import annotations

import base64

import pytest
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.application.secrets import ResolutionRequest, SecretVault, StoreSecretCommand
from factory_core.config.secrets import SecretsSettings
from factory_core.domain.ids import ProjectId, new_id, new_project_id, new_user_id
from factory_core.errors import NotFoundError
from factory_core.persistence import ProjectRepository, UserRepository
from factory_core.persistence.models_secrets import SecretAccessLogRow
from factory_core.persistence.repositories.secrets import (
    ProjectKeyRepository,
    SecretAccessLogRepository,
    SecretRepository,
)
from factory_core.security.keyring import build_keyring
from factory_core.security.references import (
    SecretReference,
    SecretSink,
    SinkNotAllowedError,
    TracedContextError,
    traced_context,
)

pytestmark = pytest.mark.integration

SECRET_VALUE = "sk-a-very-real-looking-provider-key-9182"


def _keyring(active: str = "v1", seed: int = 0):  # type: ignore[no-untyped-def]
    material = base64.b64encode(bytes((seed + i) % 256 for i in range(32))).decode("ascii")
    return build_keyring(SecretsSettings(_env_file=None, master_key=f"{active}:{material}"))  # type: ignore[arg-type]


async def _make_project(session: AsyncSession) -> ProjectId:
    """Create a user and a project to hang secrets from.

    Built through the repositories rather than raw ORM rows so the user is flushed
    before the project references it, matching how the rest of the integration suite
    creates its fixtures.
    """
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=f"owner-{new_id().hex[:8]}@example.com",
        display_name="Owner",
        password_hash="$argon2id$fake",
    )
    project = await ProjectRepository(session, owner_id=user.id).create(
        project_id=new_project_id(),
        name="Vault Project",
        slug=f"vault-{new_id().hex[:8]}",
        description="",
    )
    return project.id


def _vault(session: AsyncSession, project_id: ProjectId) -> SecretVault:
    return SecretVault(
        secrets=SecretRepository(session, project_id=project_id),
        project_keys=ProjectKeyRepository(session),
        access_log=SecretAccessLogRepository(session),
        keyring=_keyring(),
    )


def _request(purpose: str = "deploy to staging") -> ResolutionRequest:
    return ResolutionRequest(purpose=purpose, actor_type="user", actor_id="tester")


@pytest.mark.security
class TestIsolation:
    async def test_one_project_cannot_read_anothers_secret(self, session: AsyncSession) -> None:
        first = await _make_project(session)
        second = await _make_project(session)
        await _vault(session, first).store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE))
        )

        with pytest.raises(NotFoundError):
            await _vault(session, second).resolve(
                "API_KEY", sink=SecretSink.PROVIDER_ENV, request=_request()
            )

    async def test_a_reference_for_another_project_is_refused(self, session: AsyncSession) -> None:
        """Reported as not-found so it cannot be used to discover other projects' names."""
        first = await _make_project(session)
        second = await _make_project(session)
        await _vault(session, first).store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE))
        )

        with pytest.raises(NotFoundError):
            await _vault(session, second).resolve_reference(
                SecretReference.build(str(first), "API_KEY"),
                sink=SecretSink.PROVIDER_ENV,
                request=_request(),
            )

    async def test_each_project_gets_its_own_dek(self, session: AsyncSession) -> None:
        """Per-project keys mean one compromised DEK reveals nothing about another."""
        first = await _make_project(session)
        second = await _make_project(session)
        await _vault(session, first).store(StoreSecretCommand(name="K", value=SecretStr("a")))
        await _vault(session, second).store(StoreSecretCommand(name="K", value=SecretStr("a")))

        keys = ProjectKeyRepository(session)
        first_key = await keys.get(first)
        second_key = await keys.get(second)

        assert first_key is not None
        assert second_key is not None
        assert first_key.wrapped_dek != second_key.wrapped_dek


@pytest.mark.security
class TestAuditTrail:
    async def test_a_granted_resolution_is_audited(self, session: AsyncSession) -> None:
        """The acceptance criterion: attributable to actor, purpose and run."""
        project_id = await _make_project(session)
        vault = _vault(session, project_id)
        await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE)))

        await vault.resolve(
            "API_KEY",
            sink=SecretSink.MIGRATION_CONNECTION,
            request=_request("apply migration 0007"),
        )

        row = (
            await session.execute(
                select(SecretAccessLogRow).where(SecretAccessLogRow.project_id == project_id)
            )
        ).scalar_one()
        assert row.granted is True
        assert row.secret_name == "API_KEY"
        assert row.sink == "migration_connection"
        assert row.purpose == "apply migration 0007"
        assert row.actor_id == "tester"

    async def test_a_refused_sink_is_audited(self, session: AsyncSession) -> None:
        """The denied attempt is the row an investigation wants most."""
        project_id = await _make_project(session)
        vault = _vault(session, project_id)
        await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE)))

        with pytest.raises(SinkNotAllowedError):
            await vault.resolve("API_KEY", sink="not_a_sink", request=_request())  # type: ignore[arg-type]

        row = (
            await session.execute(
                select(SecretAccessLogRow).where(SecretAccessLogRow.granted.is_(False))
            )
        ).scalar_one()
        assert row.secret_name == "API_KEY"

    async def test_a_traced_context_refusal_is_audited(self, session: AsyncSession) -> None:
        project_id = await _make_project(session)
        vault = _vault(session, project_id)
        await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE)))

        with traced_context(), pytest.raises(TracedContextError):
            await vault.resolve("API_KEY", sink=SecretSink.SANDBOX_ENV, request=_request())

        denied = (
            await session.execute(
                select(SecretAccessLogRow).where(SecretAccessLogRow.granted.is_(False))
            )
        ).scalar_one()
        assert denied.sink == "sandbox_env"

    async def test_a_missing_secret_is_audited(self, session: AsyncSession) -> None:
        """A resolution attempt for a name that does not exist is still an attempt."""
        project_id = await _make_project(session)

        with pytest.raises(NotFoundError):
            await _vault(session, project_id).resolve(
                "NEVER_STORED", sink=SecretSink.PROVIDER_ENV, request=_request()
            )

        row = (
            await session.execute(
                select(SecretAccessLogRow).where(SecretAccessLogRow.secret_name == "NEVER_STORED")
            )
        ).scalar_one()
        assert row.granted is False
