"""Master-key rotation against a real database [F-201, F-216].

Executes the procedure from ``docs/runbooks/key-management.md`` end to end: store a
secret under `v1`, deploy `v2` with `v1` retired, re-wrap, drop `v1`, and confirm the
secret is still readable throughout.

The acceptance criterion for F-216 is "rotation procedure executed successfully once".
This is that execution, automated so it stays true.
"""

from __future__ import annotations

import base64

import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from factory_core.application.secrets import ResolutionRequest, SecretVault, StoreSecretCommand
from factory_core.config.secrets import SecretsSettings
from factory_core.domain.ids import ProjectId, new_id, new_project_id, new_user_id
from factory_core.persistence import ProjectRepository, UserRepository
from factory_core.persistence.repositories.secrets import (
    ProjectKeyRepository,
    SecretAccessLogRepository,
    SecretRepository,
)
from factory_core.security.envelope import DecryptionError
from factory_core.security.keyring import KeyRing, build_keyring
from factory_core.security.references import SecretSink

pytestmark = pytest.mark.integration

SECRET_VALUE = "sk-value-that-must-survive-rotation-4417"

V1 = base64.b64encode(bytes((0 + i) % 256 for i in range(32))).decode("ascii")
V2 = base64.b64encode(bytes((90 + i) % 256 for i in range(32))).decode("ascii")


def _ring(active: str, previous: str | None = None) -> KeyRing:
    return build_keyring(
        SecretsSettings(_env_file=None, master_key=active, previous_keys=previous)  # type: ignore[arg-type]
    )


async def _make_project(session: AsyncSession) -> ProjectId:
    user = await UserRepository(session).create(
        user_id=new_user_id(),
        email=f"owner-{new_id().hex[:8]}@example.com",
        display_name="Owner",
        password_hash="$argon2id$fake",
    )
    project = await ProjectRepository(session, owner_id=user.id).create(
        project_id=new_project_id(),
        name="Rotation",
        slug=f"rot-{new_id().hex[:8]}",
        description="",
    )
    return project.id


def _vault(session: AsyncSession, project_id: ProjectId, ring: KeyRing) -> SecretVault:
    return SecretVault(
        secrets=SecretRepository(session, project_id=project_id),
        project_keys=ProjectKeyRepository(session),
        access_log=SecretAccessLogRepository(session),
        keyring=ring,
    )


async def _rewrap_all(session: AsyncSession, ring: KeyRing) -> int:
    """The re-wrap sweep, mirroring scripts/rotate_master_key.py."""
    keys = ProjectKeyRepository(session)
    rewrapped = 0
    for row in await keys.list_on_version("v1"):
        row.wrapped_dek = ring.rewrap_dek(row.wrapped_dek, project_id=str(row.project_id))
        row.key_version = ring.active_version
        rewrapped += 1
    await session.flush()
    return rewrapped


class TestRotationProcedure:
    async def test_the_full_procedure(self, session: AsyncSession) -> None:
        """Steps 2-5 of the runbook, in order, asserting readability at every stage."""
        project_id = await _make_project(session)
        request = ResolutionRequest(purpose="rotation test", actor_type="system")

        # --- Before rotation: stored under v1 ---
        v1_only = _ring(f"v1:{V1}")
        await _vault(session, project_id, v1_only).store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE))
        )
        key_row = await ProjectKeyRepository(session).get(project_id)
        assert key_row is not None
        assert key_row.key_version == "v1"

        # --- Step 2: deploy v2 active, v1 retired. Nothing re-wrapped yet. ---
        rotating = _ring(f"v2:{V2}", f"v1:{V1}")
        still_readable = await _vault(session, project_id, rotating).resolve(
            "API_KEY", sink=SecretSink.PROVIDER_ENV, request=request
        )
        assert still_readable.get_secret_value() == SECRET_VALUE, (
            "existing secrets must stay readable before the sweep runs"
        )

        # --- Step 3: re-wrap ---
        assert await _rewrap_all(session, rotating) == 1

        # --- Step 4: nothing references v1 ---
        assert await ProjectKeyRepository(session).list_on_version("v1") == []
        refreshed = await ProjectKeyRepository(session).get(project_id)
        assert refreshed is not None
        assert refreshed.key_version == "v2"

        # --- Step 5: drop v1 entirely. The secret must still decrypt. ---
        v2_only = _ring(f"v2:{V2}")
        after = await _vault(session, project_id, v2_only).resolve(
            "API_KEY", sink=SecretSink.PROVIDER_ENV, request=request
        )
        assert after.get_secret_value() == SECRET_VALUE

    async def test_the_sweep_is_idempotent(self, session: AsyncSession) -> None:
        """Re-running after an interruption must be safe — the runbook promises it."""
        project_id = await _make_project(session)
        await _vault(session, project_id, _ring(f"v1:{V1}")).store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE))
        )
        rotating = _ring(f"v2:{V2}", f"v1:{V1}")

        first = await _rewrap_all(session, rotating)
        second = await _rewrap_all(session, rotating)

        assert first == 1
        assert second == 0, "a second sweep must find nothing to do"

    async def test_values_written_after_rotation_use_the_new_key(
        self, session: AsyncSession
    ) -> None:
        project_id = await _make_project(session)
        rotating = _ring(f"v2:{V2}", f"v1:{V1}")

        await _vault(session, project_id, rotating).store(
            StoreSecretCommand(name="NEW_KEY", value=SecretStr("fresh"))
        )

        row = await ProjectKeyRepository(session).get(project_id)
        assert row is not None
        assert row.key_version == "v2"

    @pytest.mark.failure
    async def test_dropping_the_old_key_too_early_fails_closed(self, session: AsyncSession) -> None:
        """Step 5 before step 3 — the mistake the runbook's step 4 check exists to catch."""
        project_id = await _make_project(session)
        await _vault(session, project_id, _ring(f"v1:{V1}")).store(
            StoreSecretCommand(name="API_KEY", value=SecretStr(SECRET_VALUE))
        )

        premature = _ring(f"v2:{V2}")  # v1 dropped without re-wrapping

        with pytest.raises(DecryptionError):
            await _vault(session, project_id, premature).resolve(
                "API_KEY",
                sink=SecretSink.PROVIDER_ENV,
                request=ResolutionRequest(purpose="premature", actor_type="system"),
            )
