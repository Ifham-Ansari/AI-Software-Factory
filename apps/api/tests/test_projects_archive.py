"""Archiving and unarchiving over HTTP.

Split from ``test_projects_api.py`` to keep both within the file-size rule, and because
the round trip is a story of its own: archiving is only worth having if a project can come
back, and that is what these assert end to end.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


class TestUnarchive:
    async def test_round_trip_returns_the_project_to_draft(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")
        await client.post(f"/projects/{project['id']}/archive", headers=headers)

        response = await client.post(f"/projects/{project['id']}/unarchive", headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "draft"
        # Cleared, not merely stale: the field records the archive a project is in, and a
        # restored project is in none.
        assert response.json()["archived_at"] is None

    async def test_a_restored_project_accepts_writes_again(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """The point of the endpoint. A status flip that left the project read-only would
        pass the test above and still be useless."""
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")
        await client.post(f"/projects/{project['id']}/archive", headers=headers)
        await client.post(f"/projects/{project['id']}/unarchive", headers=headers)

        response = await client.patch(
            f"/projects/{project['id']}", headers=headers, json={"name": "Changed"}
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Changed"

    @pytest.mark.failure
    async def test_unarchiving_a_live_project_is_rejected(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")

        response = await client.post(f"/projects/{project['id']}/unarchive", headers=headers)

        assert response.status_code == 422

    @pytest.mark.security
    async def test_another_users_archived_project_is_not_found(
        self, client: AsyncClient, api
    ) -> None:  # type: ignore[no-untyped-def]
        """404, not 403: existence is itself information about someone else's account."""
        owner = await api.registered_headers("grace@example.com")
        stranger = await api.registered_headers("ada@example.com")
        project = await api.create_project(owner, "Theirs")
        await client.post(f"/projects/{project['id']}/archive", headers=owner)

        response = await client.post(f"/projects/{project['id']}/unarchive", headers=stranger)

        assert response.status_code == 404


class TestArchivedProjectsRemainVisible:
    async def test_archived_projects_can_be_listed(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """A project nobody can find again has been deleted, whatever the status says."""
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Filed Away")
        await client.post(f"/projects/{project['id']}/archive", headers=headers)

        response = await client.get("/projects?status=archived", headers=headers)

        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert "Filed Away" in names

    async def test_the_default_listing_still_shows_them(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """No status filter means every project, archived or not — so a user who archives
        something without realising can still see where it went."""
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Filed Away")
        await client.post(f"/projects/{project['id']}/archive", headers=headers)

        response = await client.get("/projects", headers=headers)

        names = [item["name"] for item in response.json()["items"]]
        assert "Filed Away" in names
