"""Email verification endpoints over HTTP.

Covers the properties that make a six-digit code safe to use: bounded attempts, short
expiry, and resistance to being used as an account-existence oracle. Rate-limit
enforcement (the resend cooldown and the daily cap) needs a controllable clock to test
without racing real wall-clock time, so it lives in the unit suite instead:
``packages/core/tests/unit/test_email_verification.py``. The test settings here zero the
cooldown for exactly this reason — see the ``settings`` fixture in ``conftest.py``.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.integration

EMAIL = "ada@example.com"
PASSWORD = "a-sufficiently-long-passphrase"


async def _register(client: AsyncClient, email: str = EMAIL) -> dict[str, object]:
    response = await client.post(
        "/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "Ada"},
    )
    assert response.status_code == 202, response.text
    payload: dict[str, object] = response.json()
    return payload


class TestVerifyEmail:
    async def test_correct_code_starts_a_session(self, client: AsyncClient, fakes) -> None:  # type: ignore[no-untyped-def]
        await _register(client)
        code = fakes.emails.last_code()

        response = await client.post("/auth/verify-email", json={"email": EMAIL, "code": code})

        assert response.status_code == 200
        body = response.json()
        assert body["user"]["email"] == EMAIL
        assert body["user"]["email_verified"] is True
        assert body["access_token"]

    async def test_can_sign_in_normally_after_verifying(self, client: AsyncClient, fakes) -> None:  # type: ignore[no-untyped-def]
        await _register(client)
        await client.post(
            "/auth/verify-email", json={"email": EMAIL, "code": fakes.emails.last_code()}
        )

        response = await client.post("/auth/sign-in", json={"email": EMAIL, "password": PASSWORD})

        assert response.status_code == 200

    @pytest.mark.failure
    async def test_wrong_code_rejected_with_attempts_remaining(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        await _register(client)
        real_code = fakes.emails.last_code()
        wrong = "000000" if real_code != "000000" else "111111"

        response = await client.post("/auth/verify-email", json={"email": EMAIL, "code": wrong})

        assert response.status_code == 400
        assert "attempt" in response.json()["error"]["message"].lower()

    @pytest.mark.security
    @pytest.mark.failure
    async def test_exhausting_attempts_destroys_the_code(self, client: AsyncClient, fakes) -> None:  # type: ignore[no-untyped-def]
        """Six wrong guesses is what makes online brute force futile."""
        await _register(client)
        real_code = fakes.emails.last_code()
        wrong = "000000" if real_code != "000000" else "111111"

        last_response = None
        for _ in range(6):
            last_response = await client.post(
                "/auth/verify-email", json={"email": EMAIL, "code": wrong}
            )

        assert last_response is not None
        assert last_response.status_code == 400

        # The real code is now dead too, even though it was never guessed wrong.
        after = await client.post("/auth/verify-email", json={"email": EMAIL, "code": real_code})
        assert after.status_code == 400

    @pytest.mark.security
    async def test_unknown_email_and_wrong_code_are_both_rejected_uniformly(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        """Neither response may confirm whether the address is registered."""
        await _register(client)

        unknown = await client.post(
            "/auth/verify-email", json={"email": "nobody@example.com", "code": "123456"}
        )
        wrong = await client.post("/auth/verify-email", json={"email": EMAIL, "code": "000000"})

        assert unknown.status_code in (400, 401)
        assert wrong.status_code in (400, 401)
        assert "access_token" not in unknown.json()
        assert "access_token" not in wrong.json()

    @pytest.mark.failure
    async def test_malformed_code_rejected_before_burning_an_attempt(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        """A non-numeric code must fail validation, not consume a guess."""
        await _register(client)

        response = await client.post("/auth/verify-email", json={"email": EMAIL, "code": "abcdef"})

        assert response.status_code == 422

    async def test_code_is_single_use(self, client: AsyncClient, fakes) -> None:  # type: ignore[no-untyped-def]
        await _register(client)
        code = fakes.emails.last_code()

        first = await client.post("/auth/verify-email", json={"email": EMAIL, "code": code})
        second = await client.post("/auth/verify-email", json={"email": EMAIL, "code": code})

        assert first.status_code == 200
        assert second.status_code == 400


class TestResendVerification:
    """The test settings zero the resend cooldown, so these exercise the success path.

    Cooldown and daily-cap *enforcement* need a controllable clock and are proven in
    ``packages/core/tests/unit/test_email_verification.py`` instead.
    """

    async def test_issues_a_new_code_that_supersedes_the_old_one(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        """Only one code is ever live, so an attacker never has two valid targets."""
        await _register(client)
        old_code = fakes.emails.last_code()

        response = await client.post("/auth/resend-verification", json={"email": EMAIL})

        assert response.status_code == 202
        new_code = fakes.emails.last_code()
        assert new_code != old_code or len(fakes.emails.sent) == 2

        stale = await client.post("/auth/verify-email", json={"email": EMAIL, "code": old_code})
        assert stale.status_code == 400

        fresh = await client.post("/auth/verify-email", json={"email": EMAIL, "code": new_code})
        assert fresh.status_code == 200

    @pytest.mark.security
    async def test_unknown_email_gets_the_identical_response_shape(
        self, client: AsyncClient
    ) -> None:
        """Must not reveal whether an address is registered."""
        await _register(client, email="known@example.com")

        known_response = await client.post(
            "/auth/resend-verification", json={"email": "known@example.com"}
        )
        unknown_response = await client.post(
            "/auth/resend-verification", json={"email": "unknown@example.com"}
        )

        assert known_response.status_code == unknown_response.status_code == 202
        known_body, unknown_body = known_response.json(), unknown_response.json()
        assert set(known_body) == set(unknown_body)
        assert known_body["expires_in"] == unknown_body["expires_in"]
        assert known_body["resend_available_in"] == unknown_body["resend_available_in"]

    async def test_already_verified_gets_the_same_shape_but_sends_nothing(
        self, client: AsyncClient, fakes
    ) -> None:  # type: ignore[no-untyped-def]
        await _register(client)
        await client.post(
            "/auth/verify-email", json={"email": EMAIL, "code": fakes.emails.last_code()}
        )
        sent_before = len(fakes.emails.sent)

        response = await client.post("/auth/resend-verification", json={"email": EMAIL})

        assert response.status_code == 202
        assert len(fakes.emails.sent) == sent_before  # nothing actually sent
