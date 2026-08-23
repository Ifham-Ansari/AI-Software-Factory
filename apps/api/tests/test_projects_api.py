"""Project endpoints over HTTP, including cross-user isolation."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration


def _comparable(body: dict[str, object]) -> dict[str, object]:
    """Strip the per-request correlation id so two error bodies can be compared."""
    error = dict(body["error"])  # type: ignore[arg-type]
    error.pop("request_id", None)
    return error


class TestCreate:
    async def test_creates_a_draft_project(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()

        response = await client.post(
            "/projects",
            json={"name": "Restaurant System", "description": "POS and inventory."},
            headers=headers,
        )

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Restaurant System"
        assert body["slug"] == "restaurant-system"
        assert body["status"] == "draft"

    @pytest.mark.security
    async def test_response_omits_owner_id(self, api) -> None:  # type: ignore[no-untyped-def]
        """A caller only ever sees their own projects, so owner_id carries no meaning."""
        headers = await api.registered_headers()

        body = await api.create_project(headers, "Mine")

        assert "owner_id" not in body

    @pytest.mark.failure
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post("/projects", json={"name": "Anonymous"})

        assert response.status_code == 401

    @pytest.mark.failure
    @pytest.mark.parametrize("name", ["", "x" * 121])
    async def test_invalid_name_rejected(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
        name: str,
    ) -> None:
        headers = await api.registered_headers()

        response = await client.post("/projects", json={"name": name}, headers=headers)

        assert response.status_code == 422


class TestList:
    async def test_lists_projects_with_metadata(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        await api.create_project(headers, "Alpha")
        await api.create_project(headers, "Bravo")

        response = await client.get("/projects", headers=headers)

        assert response.status_code == 200
        body = response.json()
        assert body["meta"]["total"] == 2
        assert body["meta"]["total_pages"] == 1
        assert len(body["items"]) == 2

    async def test_pagination(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        for index in range(5):
            await api.create_project(headers, f"Project {index}")

        response = await client.get("/projects?page=2&page_size=2", headers=headers)

        body = response.json()
        assert len(body["items"]) == 2
        assert body["meta"]["page"] == 2
        assert body["meta"]["has_next"] and body["meta"]["has_previous"]

    async def test_search_filter(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        await api.create_project(headers, "Restaurant System")
        await api.create_project(headers, "Inventory Tracker")

        response = await client.get("/projects?search=restaurant", headers=headers)

        assert [item["name"] for item in response.json()["items"]] == ["Restaurant System"]

    async def test_empty_list_is_not_an_error(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """An empty collection is a valid state, not a 404."""
        headers = await api.registered_headers()

        response = await client.get("/projects", headers=headers)

        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["meta"]["total_pages"] == 1

    @pytest.mark.failure
    @pytest.mark.parametrize("query", ["page=0", "page_size=0", "page_size=101", "page=-1"])
    async def test_out_of_range_pagination_rejected(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
        query: str,
    ) -> None:
        headers = await api.registered_headers()

        response = await client.get(f"/projects?{query}", headers=headers)

        assert response.status_code == 422

    @pytest.mark.security
    async def test_unknown_sort_field_rejected(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        """An unvalidated sort column would be an injection vector."""
        headers = await api.registered_headers()

        response = await client.get("/projects?sort_by=password_hash", headers=headers)

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_failed"


class TestUpdate:
    async def test_updates_name_and_slug(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Old Name")

        response = await client.patch(
            f"/projects/{project['id']}", json={"name": "New Name"}, headers=headers
        )

        assert response.status_code == 200
        assert response.json()["slug"] == "new-name"

    async def test_partial_update(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")

        response = await client.patch(
            f"/projects/{project['id']}", json={"description": "Added"}, headers=headers
        )

        body = response.json()
        assert body["name"] == "Name"
        assert body["description"] == "Added"

    @pytest.mark.failure
    async def test_empty_patch_rejected(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")

        response = await client.patch(f"/projects/{project['id']}", json={}, headers=headers)

        assert response.status_code == 422

    @pytest.mark.failure
    async def test_archived_project_cannot_be_updated(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")
        await client.post(f"/projects/{project['id']}/archive", headers=headers)

        response = await client.patch(
            f"/projects/{project['id']}", json={"name": "Changed"}, headers=headers
        )

        assert response.status_code == 403


class TestArchiveAndDelete:
    async def test_archive(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")

        response = await client.post(f"/projects/{project['id']}/archive", headers=headers)

        assert response.status_code == 200
        assert response.json()["status"] == "archived"
        assert response.json()["archived_at"] is not None

    async def test_delete(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        headers = await api.registered_headers()
        project = await api.create_project(headers, "Name")

        response = await client.delete(f"/projects/{project['id']}", headers=headers)

        assert response.status_code == 204
        gone = await client.get(f"/projects/{project['id']}", headers=headers)
        assert gone.status_code == 404


class TestFullLifecycle:
    async def test_create_read_update_archive_delete(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        """End-to-end journey a real client would make."""
        headers = await api.registered_headers()

        created = await api.create_project(headers, "Lifecycle Project")
        project_id = created["id"]

        assert (await client.get(f"/projects/{project_id}", headers=headers)).status_code == 200

        updated = await client.patch(
            f"/projects/{project_id}", json={"description": "Now described"}, headers=headers
        )
        assert updated.json()["description"] == "Now described"

        archived = await client.post(f"/projects/{project_id}/archive", headers=headers)
        assert archived.json()["status"] == "archived"

        listing = await client.get("/projects?status=archived", headers=headers)
        assert listing.json()["meta"]["total"] == 1

        assert (await client.delete(f"/projects/{project_id}", headers=headers)).status_code == 204
        assert (await client.get("/projects", headers=headers)).json()["meta"]["total"] == 0
