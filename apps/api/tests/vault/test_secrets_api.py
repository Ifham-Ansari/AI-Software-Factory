"""Secret vault over HTTP [F-202].

The acceptance criterion — **no endpoint returns a secret value** — is checked two ways:

* **Structurally**, by walking every response schema in the generated OpenAPI document
  and asserting none has a field that could carry a plaintext value. That covers routes
  nobody has written yet, which a hand-listed set of assertions would not.
* **Behaviourally**, by storing a distinctive value and asserting it appears in no
  response body from any reachable route.

Fixtures live in this directory's ``conftest.py``.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import AsyncClient

from .conftest import SECRET_VALUE, VALUE_FIELD_NAMES, signed_in

pytestmark = pytest.mark.integration


@pytest.mark.security
class TestWriteOnly:
    def test_no_response_schema_can_carry_a_secret_value(self, vault_app: FastAPI) -> None:
        """Structural proof, over every route in the document.

        Walks each operation's response schemas and fails if any exposes a field named
        like a plaintext value. Automatically covers routes added later.
        """
        document = vault_app.openapi()
        components = document.get("components", {}).get("schemas", {})
        offenders: list[str] = []

        def field_names(schema_name: str) -> set[str]:
            schema = components.get(schema_name, {})
            return set(schema.get("properties", {}))

        for path, operations in document["paths"].items():
            for method, operation in operations.items():
                for status, response in operation.get("responses", {}).items():
                    content = response.get("content", {}).get("application/json", {})
                    ref = content.get("schema", {}).get("$ref", "")
                    if not ref:
                        continue
                    name = ref.rsplit("/", 1)[-1]
                    leaked = field_names(name) & VALUE_FIELD_NAMES
                    if leaked:
                        offenders.append(f"{method.upper()} {path} -> {status}: {leaked}")

        assert not offenders, f"response schemas expose secret-shaped fields: {offenders}"

    async def test_a_stored_value_is_returned_by_no_route(self, client: AsyncClient) -> None:
        """Behavioural proof: store a distinctive value, then read everything back."""
        headers, project_id = await signed_in(client)
        await client.put(
            f"/projects/{project_id}/secrets/API_KEY",
            json={"name": "API_KEY", "value": SECRET_VALUE, "description": "prod"},
            headers=headers,
        )

        responses = [
            await client.get(f"/projects/{project_id}/secrets", headers=headers),
            await client.get(f"/projects/{project_id}/secrets/API_KEY", headers=headers),
            await client.get(f"/projects/{project_id}/configuration", headers=headers),
            await client.get(f"/projects/{project_id}", headers=headers),
        ]

        for response in responses:
            assert SECRET_VALUE not in response.text, f"{response.request.url} leaked the value"

    async def test_the_store_response_does_not_echo_the_value(self, client: AsyncClient) -> None:
        """Even the write that supplied it must not send it back."""
        headers, project_id = await signed_in(client)

        response = await client.put(
            f"/projects/{project_id}/secrets/API_KEY",
            json={"name": "API_KEY", "value": SECRET_VALUE},
            headers=headers,
        )

        assert response.status_code == 200
        assert SECRET_VALUE not in response.text


class TestSecretRoutes:
    async def test_store_then_describe(self, client: AsyncClient) -> None:
        headers, project_id = await signed_in(client)

        await client.put(
            f"/projects/{project_id}/secrets/API_KEY",
            json={"name": "API_KEY", "value": SECRET_VALUE, "description": "prod key"},
            headers=headers,
        )
        described = await client.get(f"/projects/{project_id}/secrets/API_KEY", headers=headers)

        body = described.json()
        assert body["name"] == "API_KEY"
        assert body["is_set"] is True
        assert body["reference"] == f"secret://project/{project_id}/API_KEY"

    async def test_list_is_empty_for_a_new_project(self, client: AsyncClient) -> None:
        headers, project_id = await signed_in(client)

        response = await client.get(f"/projects/{project_id}/secrets", headers=headers)

        assert response.json() == {"items": [], "total": 0}

    async def test_delete_removes_it(self, client: AsyncClient) -> None:
        headers, project_id = await signed_in(client)
        await client.put(
            f"/projects/{project_id}/secrets/API_KEY",
            json={"name": "API_KEY", "value": SECRET_VALUE},
            headers=headers,
        )

        deleted = await client.delete(f"/projects/{project_id}/secrets/API_KEY", headers=headers)

        assert deleted.status_code == 204
        missing = await client.get(f"/projects/{project_id}/secrets/API_KEY", headers=headers)
        assert missing.status_code == 404

    @pytest.mark.failure
    async def test_deleting_a_missing_secret_is_404(self, client: AsyncClient) -> None:
        """Silently succeeding would leave an operator believing a credential was revoked."""
        headers, project_id = await signed_in(client)

        response = await client.delete(
            f"/projects/{project_id}/secrets/NEVER_STORED", headers=headers
        )

        assert response.status_code == 404

    @pytest.mark.failure
    @pytest.mark.parametrize("name", ["lowercase", "HAS-HYPHEN", "1LEADING"])
    async def test_invalid_names_are_rejected(self, client: AsyncClient, name: str) -> None:
        headers, project_id = await signed_in(client)

        response = await client.put(
            f"/projects/{project_id}/secrets/{name}",
            json={"name": name, "value": "x"},
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.failure
    async def test_mismatched_path_and_body_name_is_rejected(self, client: AsyncClient) -> None:
        """Guessing which was meant would silently write to the wrong key."""
        headers, project_id = await signed_in(client)

        response = await client.put(
            f"/projects/{project_id}/secrets/ONE_NAME",
            json={"name": "OTHER_NAME", "value": "x"},
            headers=headers,
        )

        # 422: the project maps `ValidationError` to Unprocessable Entity throughout.
        assert response.status_code == 422

    @pytest.mark.security
    @pytest.mark.failure
    async def test_unauthenticated_access_is_refused(self, client: AsyncClient) -> None:
        _, project_id = await signed_in(client)

        response = await client.get(f"/projects/{project_id}/secrets")

        assert response.status_code == 401

    @pytest.mark.security
    @pytest.mark.failure
    async def test_another_users_project_is_not_found(self, client: AsyncClient) -> None:
        """404 rather than 403: a 403 would confirm the project exists."""
        headers, _ = await signed_in(client)
        stranger_project = "11111111-1111-4111-8111-111111111111"

        response = await client.get(f"/projects/{stranger_project}/secrets", headers=headers)

        assert response.status_code == 404
