"""Convenience wrappers over common request sequences, shared across the API test suite.

Split out of ``conftest.py`` so fixture wiring and request helpers stay two separate
concerns. Not a fixture itself — ``conftest.py`` exposes an instance through the ``api``
fixture, which is how every test file receives it.
"""

from __future__ import annotations

from httpx import AsyncClient

from factory_core.testing import RecordingEmailSender

TEST_PASSWORD = "a-sufficiently-long-passphrase"
TEST_EMAIL = "ada@example.com"


class ApiHelper:
    """Convenience wrappers over common request sequences."""

    def __init__(self, client: AsyncClient, emails: RecordingEmailSender) -> None:
        self.client = client
        self.emails = emails

    async def register_only(
        self,
        *,
        email: str = TEST_EMAIL,
        password: str = TEST_PASSWORD,
        display_name: str = "Ada Lovelace",
    ) -> dict[str, object]:
        """Create an account without verifying it. Returns the challenge payload."""
        response = await self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "display_name": display_name},
        )
        assert response.status_code == 202, response.text
        payload: dict[str, object] = response.json()
        return payload

    async def register(
        self,
        *,
        email: str = TEST_EMAIL,
        password: str = TEST_PASSWORD,
        display_name: str = "Ada Lovelace",
    ) -> dict[str, object]:
        """Register, redeem the emailed code, and return the session payload.

        Most tests care about being signed in, not about the verification step itself;
        that has its own suite.
        """
        await self.register_only(email=email, password=password, display_name=display_name)
        response = await self.client.post(
            "/auth/verify-email",
            json={"email": email, "code": self.emails.last_code()},
        )
        assert response.status_code == 200, response.text
        payload: dict[str, object] = response.json()
        return payload

    @staticmethod
    def auth_header(session: dict[str, object]) -> dict[str, str]:
        """Build an Authorization header from a session payload."""
        return {"Authorization": f"Bearer {session['access_token']}"}

    async def registered_headers(self, email: str = TEST_EMAIL) -> dict[str, str]:
        """Register an account and return ready-to-use auth headers."""
        return self.auth_header(await self.register(email=email))

    async def create_project(
        self, headers: dict[str, str], name: str, **fields: object
    ) -> dict[str, object]:
        """Create a project and return it."""
        response = await self.client.post(
            "/projects", json={"name": name, **fields}, headers=headers
        )
        assert response.status_code == 201, response.text
        payload: dict[str, object] = response.json()
        return payload
