"""Cross-user isolation over HTTP.

The central security property of the platform: a caller can reach their own
projects and nothing else, and cannot tell the difference between a project that
does not exist and one belonging to somebody else.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _comparable(body: dict[str, object]) -> dict[str, object]:
    """Strip the per-request correlation id so two error bodies can be compared."""
    error = dict(body["error"])  # type: ignore[arg-type]
    error.pop("request_id", None)
    return error


@pytest.mark.security
class TestIsolation:
    """The central security property: one user cannot reach another user's projects."""

    async def test_list_shows_only_own_projects(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        ada = await api.registered_headers("ada@example.com")
        grace = await api.registered_headers("grace@example.com")
        await api.create_project(ada, "Ada's Project")
        await api.create_project(grace, "Grace's Project")

        response = await client.get("/projects", headers=ada)

        assert [item["name"] for item in response.json()["items"]] == ["Ada's Project"]

    async def test_cannot_read_another_users_project(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        ada = await api.registered_headers("ada@example.com")
        grace = await api.registered_headers("grace@example.com")
        theirs = await api.create_project(grace, "Private")

        response = await client.get(f"/projects/{theirs['id']}", headers=ada)

        assert response.status_code == 404

    async def test_not_found_rather_than_forbidden(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """403 would confirm the id is real and enable enumeration."""
        ada = await api.registered_headers("ada@example.com")
        grace = await api.registered_headers("grace@example.com")
        theirs = await api.create_project(grace, "Private")

        forbidden = await client.get(f"/projects/{theirs['id']}", headers=ada)
        missing = await client.get("/projects/00000000-0000-4000-8000-000000000000", headers=ada)

        assert forbidden.status_code == missing.status_code == 404
        # request_id is expected to differ; everything a caller could distinguish on
        # must be byte-identical.
        assert _comparable(forbidden.json()) == _comparable(missing.json())

    async def test_malformed_id_is_also_not_found(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """A 422 for a malformed id tells a prober their guess was shaped right."""
        headers = await api.registered_headers()

        response = await client.get("/projects/not-a-uuid", headers=headers)

        assert response.status_code == 404

    async def test_cannot_update_another_users_project(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        ada = await api.registered_headers("ada@example.com")
        grace = await api.registered_headers("grace@example.com")
        theirs = await api.create_project(grace, "Private")

        response = await client.patch(
            f"/projects/{theirs['id']}", json={"name": "Hijacked"}, headers=ada
        )

        assert response.status_code == 404

    async def test_cannot_delete_another_users_project(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        ada = await api.registered_headers("ada@example.com")
        grace = await api.registered_headers("grace@example.com")
        theirs = await api.create_project(grace, "Private")

        response = await client.delete(f"/projects/{theirs['id']}", headers=ada)

        assert response.status_code == 404
        still_there = await client.get(f"/projects/{theirs['id']}", headers=grace)
        assert still_there.status_code == 200

    async def test_cannot_archive_another_users_project(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        ada = await api.registered_headers("ada@example.com")
        grace = await api.registered_headers("grace@example.com")
        theirs = await api.create_project(grace, "Private")

        response = await client.post(f"/projects/{theirs['id']}/archive", headers=ada)

        assert response.status_code == 404
