"""Project configuration requirements over HTTP [F-206].

Answers a different question from the vault tests: not "is the value safe?" but "what does
this project still need?".

The two tests worth reading store and then delete a secret. Satisfaction for a
secret-backed requirement is *derived* from whether the secret exists rather than stored
as a flag, and these prove it tracks reality in both directions.

Fixtures live in this directory's ``conftest.py``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from .conftest import signed_in

pytestmark = pytest.mark.integration


class TestConfiguration:
    async def test_requirements_start_empty(self, client: AsyncClient) -> None:
        headers, project_id = await signed_in(client)

        body = (await client.get(f"/projects/{project_id}/configuration", headers=headers)).json()

        assert body["requirements"] == []
        assert body["is_satisfied"] is True

    async def test_adding_a_requirement_reports_it_missing(self, client: AsyncClient) -> None:
        headers, project_id = await signed_in(client)

        body = (
            await client.post(
                f"/projects/{project_id}/configuration/requirements",
                json={"key": "GITHUB_TOKEN"},
                headers=headers,
            )
        ).json()

        assert body["missing"] == ["GITHUB_TOKEN"]
        assert body["is_satisfied"] is False

    async def test_storing_the_secret_satisfies_the_requirement(self, client: AsyncClient) -> None:
        """Satisfaction is derived, so it cannot disagree with what is actually stored."""
        headers, project_id = await signed_in(client)
        await client.post(
            f"/projects/{project_id}/configuration/requirements",
            json={"key": "GITHUB_TOKEN"},
            headers=headers,
        )

        await client.put(
            f"/projects/{project_id}/secrets/GITHUB_TOKEN",
            json={"name": "GITHUB_TOKEN", "value": "ghp_something"},
            headers=headers,
        )

        body = (await client.get(f"/projects/{project_id}/configuration", headers=headers)).json()
        assert body["missing"] == []
        assert body["is_satisfied"] is True

    async def test_deleting_the_secret_makes_it_missing_again(self, client: AsyncClient) -> None:
        """The reason satisfaction is derived rather than stored."""
        headers, project_id = await signed_in(client)
        await client.post(
            f"/projects/{project_id}/configuration/requirements",
            json={"key": "GITHUB_TOKEN"},
            headers=headers,
        )
        await client.put(
            f"/projects/{project_id}/secrets/GITHUB_TOKEN",
            json={"name": "GITHUB_TOKEN", "value": "ghp_something"},
            headers=headers,
        )
        await client.delete(f"/projects/{project_id}/secrets/GITHUB_TOKEN", headers=headers)

        body = (await client.get(f"/projects/{project_id}/configuration", headers=headers)).json()
        assert body["missing"] == ["GITHUB_TOKEN"]

    @pytest.mark.failure
    async def test_an_unknown_requirement_key_is_rejected(self, client: AsyncClient) -> None:
        headers, project_id = await signed_in(client)

        response = await client.post(
            f"/projects/{project_id}/configuration/requirements",
            json={"key": "NOT_IN_CATALOG"},
            headers=headers,
        )

        assert response.status_code == 422
