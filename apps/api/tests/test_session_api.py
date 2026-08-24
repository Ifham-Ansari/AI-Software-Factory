"""Session lifecycle over HTTP: refresh, sign-out, and the current-user lookup.

Split from ``test_auth_api.py``, which owns account creation and credential exchange —
this file owns what happens to a session once one exists.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

EMAIL = "ada@example.com"


class TestRefresh:
    async def test_rotates_the_token(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        session = await api.register()

        response = await client.post(
            "/auth/refresh", json={"refresh_token": session["refresh_token"]}
        )

        assert response.status_code == 200
        assert response.json()["refresh_token"] != session["refresh_token"]

    @pytest.mark.failure
    @pytest.mark.security
    async def test_reused_token_revokes_the_family(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        session = await api.register()
        rotated = await client.post(
            "/auth/refresh", json={"refresh_token": session["refresh_token"]}
        )
        current = rotated.json()["refresh_token"]

        replayed = await client.post(
            "/auth/refresh", json={"refresh_token": session["refresh_token"]}
        )

        assert replayed.status_code == 401
        assert replayed.json()["error"]["code"] == "token_reused"

        # The whole family is dead, including the legitimate holder's current token.
        after = await client.post("/auth/refresh", json={"refresh_token": current})
        assert after.status_code == 401

    @pytest.mark.failure
    async def test_unknown_token_rejected(self, client: AsyncClient) -> None:
        response = await client.post("/auth/refresh", json={"refresh_token": "nonsense"})

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "token_invalid"


class TestSignOut:
    async def test_revokes_the_session(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        session = await api.register()

        response = await client.post(
            "/auth/sign-out", json={"refresh_token": session["refresh_token"]}
        )

        assert response.status_code == 200
        replay = await client.post(
            "/auth/refresh", json={"refresh_token": session["refresh_token"]}
        )
        assert replay.status_code == 401

    async def test_unknown_token_succeeds_silently(self, client: AsyncClient) -> None:
        response = await client.post("/auth/sign-out", json={"refresh_token": "nope"})

        assert response.status_code == 200


class TestCurrentUser:
    async def test_returns_the_authenticated_user(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        session = await api.register()

        response = await client.get("/auth/me", headers=api.auth_header(session))

        assert response.status_code == 200
        assert response.json()["email"] == EMAIL

    @pytest.mark.failure
    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"Authorization": "Bearer not-a-token"},
            {"Authorization": "Basic abc"},
            {"Authorization": "Bearer "},
        ],
    )
    async def test_bad_credentials_rejected(
        self, client: AsyncClient, headers: dict[str, str]
    ) -> None:
        response = await client.get("/auth/me", headers=headers)

        assert response.status_code == 401

    @pytest.mark.failure
    @pytest.mark.security
    async def test_suspended_account_is_refused(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
        fakes,  # type: ignore[no-untyped-def]
    ) -> None:
        """Suspension must take effect immediately, not when the token expires."""
        session = await api.register()
        user_id = next(iter(fakes.users.users))
        fakes.users.suspend(user_id)

        response = await client.get("/auth/me", headers=api.auth_header(session))

        assert response.status_code == 403
