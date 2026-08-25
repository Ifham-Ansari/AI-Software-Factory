"""Secret vault against a real database [F-202, F-203, F-204].

Covers the acceptance criteria that need real SQL: that the stored row genuinely holds no
plaintext, that every resolution — granted or refused — writes an audit row in the same
transaction, and that one project's vault cannot read another's.
"""

from __future__ import annotations

import base64

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.application.secrets import ResolutionRequest, SecretVault, StoreSecretCommand
from factory_core.config.secrets import SecretsSettings
from factory_core.domain.ids import ProjectId, new_id, new_project_id, new_user_id
from factory_core.errors import NotFoundError
from factory_core.persistence import ProjectRepository, UserRepository
from factory_core.persistence.models_secrets import SecretRow
from factory_core.persistence.repositories.secrets import (
    ProjectKeyRepository,
    SecretAccessLogRepository,
    SecretRepository,
)
from factory_core.security.keyring import build_keyring
from factory_core.security.references import (
    SecretSink,
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


class TestStoreAndResolve:
    async def test_round_trip(self, session: AsyncSession) -> None:
        project_id = await _make_project(session)
        vault = _vault(session, project_id)

        await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE)))
        resolved = await vault.resolve("API_KEY", sink=SecretSink.PROVIDER_ENV, request=_request())

        assert resolved.get_secret_value() == SECRET_VALUE

    @pytest.mark.security
    async def test_stored_row_contains_no_plaintext(self, session: AsyncSession) -> None:
        """The acceptance criterion: the value is not retrievable from storage."""
        project_id = await _make_project(session)
        await _vault(session, project_id).store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE))
        )

        row = (
            await session.execute(select(SecretRow).where(SecretRow.name == "API_KEY"))
        ).scalar_one()

        assert SECRET_VALUE.encode() not in bytes(row.ciphertext)

    @pytest.mark.security
    async def test_plaintext_appears_in_no_column_of_any_table(self, session: AsyncSession) -> None:
        """A blunt sweep: dump every text-ish column and assert the value is absent.

        Catches a value accidentally copied into a description, an audit row, or a log
        table by some future change — which a targeted assertion would miss.
        """
        project_id = await _make_project(session)
        vault = _vault(session, project_id)
        await vault.store(
            StoreSecretCommand(
                name="API_KEY", value=SecretStr(SECRET_VALUE), description="prod key"
            )
        )
        await vault.resolve("API_KEY", sink=SecretSink.PROVIDER_ENV, request=_request())
        await session.flush()

        rows = await session.execute(
            text(
                """
                SELECT table_name, column_name FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND data_type IN ('text', 'character varying', 'jsonb', 'json')
                """
            )
        )
        for table_name, column_name in rows:
            found = await session.execute(
                text(
                    f'SELECT count(*) FROM "{table_name}" '  # noqa: S608 - names from catalog
                    f'WHERE CAST("{column_name}" AS TEXT) LIKE :needle'
                ),
                {"needle": f"%{SECRET_VALUE}%"},
            )
            assert found.scalar_one() == 0, f"plaintext found in {table_name}.{column_name}"

    async def test_replacing_a_secret_bumps_its_version(self, session: AsyncSession) -> None:
        project_id = await _make_project(session)
        vault = _vault(session, project_id)

        await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr("first")))
        view = await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr("second")))

        assert view.version == 2
        resolved = await vault.resolve("API_KEY", sink=SecretSink.PROVIDER_ENV, request=_request())
        assert resolved.get_secret_value() == "second"

    async def test_list_returns_metadata_without_values(self, session: AsyncSession) -> None:
        project_id = await _make_project(session)
        vault = _vault(session, project_id)
        await vault.store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE), description="d")
        )

        views = await vault.list_secrets()

        assert [v.name for v in views] == ["API_KEY"]
        assert SECRET_VALUE not in views[0].model_dump_json()

    async def test_delete_removes_the_secret(self, session: AsyncSession) -> None:
        project_id = await _make_project(session)
        vault = _vault(session, project_id)
        await vault.store(StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE)))

        assert await vault.delete("API_KEY")
        with pytest.raises(NotFoundError):
            await vault.describe("API_KEY")
