"""Registration and sign-in over HTTP."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

EMAIL = "ada@example.com"
PASSWORD = "a-sufficiently-long-passphrase"


class TestRegister:
    async def test_creates_an_unverified_account_and_sends_a_code(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Ada Lovelace"},
        )

        assert response.status_code == 202
        body = response.json()
        assert body["email"] == EMAIL
        assert body["expires_in"] > 0
        assert body["resend_available_in"] >= 0
        # No session yet: the address has not been proven.
        assert "access_token" not in body
        assert len(fakes.emails.sent) == 1
        assert fakes.emails.sent[0].to == EMAIL

    async def test_cannot_sign_in_before_verifying(self, client: AsyncClient) -> None:
        await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Ada"},
        )

        response = await client.post(
            "/auth/sign-in", json={"email": EMAIL, "password": PASSWORD}
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "email_not_verified"

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

    @pytest.mark.security
    async def test_response_never_contains_the_code(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        """The code is emailed, never returned in the API response."""
        response = await client.post(
            "/auth/register",
            json={"email": EMAIL, "password": PASSWORD, "display_name": "Ada"},
        )

        code = fakes.emails.last_code()
        assert code not in response.text

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
