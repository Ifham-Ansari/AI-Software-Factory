"""Authentication endpoints over HTTP."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

EMAIL = "ada@example.com"
PASSWORD = "a-sufficiently-long-passphrase"


class TestRegister:
    async def test_creates_account_and_returns_session(self, client: AsyncClient) -> None:
        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Ada Lovelace"},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["user"]["email"] == EMAIL
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 600

    @pytest.mark.security
    async def test_response_never_contains_password_material(self, client: AsyncClient) -> None:
        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Ada"},
        )

        raw = response.text
        assert PASSWORD not in raw
        assert "password_hash" not in raw
        assert "argon2" not in raw

    async def test_duplicate_email_conflicts(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        await api.register()

        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Ada"},
        )

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "already_exists"

    @pytest.mark.failure
    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"email": "not-an-email", "password": PASSWORD, "display_name": "A"}, "email"),
            ({"email": EMAIL, "password": "short", "display_name": "A"}, "password"),
            ({"email": EMAIL, "password": PASSWORD, "display_name": ""}, "display_name"),
        ],
    )
    async def test_invalid_input_rejected(
        self, client: AsyncClient, payload: dict[str, str], field: str
    ) -> None:
        response = await client.post("/auth/register", json=payload)

        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "validation_failed"
        assert any(item["field"] == field for item in error["fields"])

    @pytest.mark.failure
    async def test_unknown_fields_rejected(self, client: AsyncClient) -> None:
        """Silently ignoring a stray field hides client bugs and schema drift."""
        response = await client.post(
            "/auth/register",
            json={
                "email": EMAIL,
                "password": PASSWORD,
                "display_name": "Ada",
                "is_admin": True,
            },
        )

        assert response.status_code == 422


class TestSignIn:
    async def test_valid_credentials(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        await api.register()

        response = await client.post("/auth/sign-in", json={"email": EMAIL, "password": PASSWORD})

        assert response.status_code == 200
        assert response.json()["user"]["email"] == EMAIL

    async def test_email_is_case_insensitive(self, client: AsyncClient, api) -> None:  # type: ignore[no-untyped-def]
        await api.register()

        response = await client.post(
            "/auth/sign-in", json={"email": "ADA@EXAMPLE.COM", "password": PASSWORD}
        )

        assert response.status_code == 200

    @pytest.mark.failure
    @pytest.mark.security
    async def test_wrong_password_and_unknown_email_are_identical(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
    ) -> None:
        """Any observable difference turns this endpoint into an account enumerator."""
        await api.register()

        wrong = await client.post(
            "/auth/sign-in", json={"email": EMAIL, "password": "wrong-password-here"}
        )
        unknown = await client.post(
            "/auth/sign-in", json={"email": "nobody@example.com", "password": PASSWORD}
        )

        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json()["error"]["code"] == unknown.json()["error"]["code"]
        assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


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
