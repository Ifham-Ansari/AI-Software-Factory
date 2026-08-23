"""Cross-cutting HTTP behaviour: health, error envelope, correlation, redaction."""

from __future__ import annotations

import io
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from factory_api.middleware import REQUEST_ID_HEADER
from factory_core.errors import DatabaseUnavailableError
from factory_core.observability import get_redactor

pytestmark = pytest.mark.integration

EMAIL = "ada@example.com"
PASSWORD = "a-sufficiently-long-passphrase"


class TestHealth:
    async def test_liveness_needs_no_dependencies(self, client: AsyncClient) -> None:
        """Must answer even when everything downstream is broken."""
        response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["environment"] == "test"

    @pytest.mark.security
    async def test_liveness_exposes_no_configuration(self, client: AsyncClient) -> None:
        """Unauthenticated, so its body is public attack surface."""
        raw = (await client.get("/health")).text

        assert "postgresql" not in raw
        assert "secret" not in raw.lower()

    async def test_readiness_reports_dependencies(self, client: AsyncClient) -> None:
        response = await client.get("/ready")

        body = response.json()
        assert "dependencies" in body
        assert any(d["name"] == "database" for d in body["dependencies"])

    @pytest.mark.failure
    async def test_readiness_returns_503_when_a_dependency_is_down(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """A dependency outage must stop traffic without killing the process."""

        async def failing() -> None:
            raise DatabaseUnavailableError

        app.state.app_state.health.register("database", failing)

        response = await client.get("/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "unhealthy"
        database = next(d for d in body["dependencies"] if d["name"] == "database")
        assert database["status"] == "unhealthy"

    @pytest.mark.failure
    @pytest.mark.security
    async def test_readiness_failure_leaks_no_detail(
        self, app: FastAPI, client: AsyncClient
    ) -> None:
        """Driver errors routinely embed the connection string."""

        async def failing() -> None:
            raise RuntimeError("could not connect to postgresql://user:hunter2@db/prod")

        app.state.app_state.health.register("database", failing)

        raw = (await client.get("/ready")).text

        assert "hunter2" not in raw
        assert "postgresql://" not in raw


class TestErrorEnvelope:
    async def test_unknown_route_uses_the_envelope(self, client: AsyncClient) -> None:
        response = await client.get("/does-not-exist")

        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"

    async def test_method_not_allowed_uses_the_envelope(self, client: AsyncClient) -> None:
        response = await client.delete("/health")

        assert response.status_code == 405
        assert "error" in response.json()

    async def test_every_error_carries_a_request_id(self, client: AsyncClient) -> None:
        response = await client.get("/does-not-exist")

        assert response.json()["error"]["request_id"]

    @pytest.mark.failure
    async def test_malformed_json_rejected_cleanly(self, client: AsyncClient) -> None:
        response = await client.post(
            "/auth/sign-in",
            content=b"{not valid json",
            headers={"Content-Type": "application/json"},
        )

        assert response.status_code == 422
        assert "error" in response.json()

    @pytest.mark.failure
    @pytest.mark.security
    async def test_unhandled_exception_leaks_nothing(self, app: FastAPI) -> None:
        """A traceback in a response body hands over paths, versions, and often SQL."""

        @app.get("/boom")
        async def boom() -> None:
            raise RuntimeError("internal detail: postgresql://user:hunter2@db/prod")

        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with (
            app.router.lifespan_context(app),
            AsyncClient(transport=transport, base_url="http://test") as http,
        ):
            response = await http.get("/boom")

        assert response.status_code == 500
        raw = response.text
        assert response.json()["error"]["code"] == "internal_error"
        assert "hunter2" not in raw
        assert "RuntimeError" not in raw
        assert "Traceback" not in raw


class TestCorrelation:
    async def test_response_carries_a_request_id_header(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.headers[REQUEST_ID_HEADER]

    async def test_inbound_request_id_is_honoured(self, client: AsyncClient) -> None:
        """Lets a trace span a reverse proxy or a calling service."""
        response = await client.get("/health", headers={REQUEST_ID_HEADER: "abc-123"})

        assert response.headers[REQUEST_ID_HEADER] == "abc-123"

    @pytest.mark.security
    @pytest.mark.parametrize(
        "hostile",
        ["a b", "x\nInjected: true", "'; DROP TABLE users--", "x" * 200, "<script>"],
    )
    async def test_hostile_request_id_is_discarded(self, client: AsyncClient, hostile: str) -> None:
        """The value reaches logs and a response header, so it is replaced, not escaped."""
        response = await client.get("/health", headers={REQUEST_ID_HEADER: hostile})

        assert response.headers[REQUEST_ID_HEADER] != hostile

    async def test_each_request_gets_a_distinct_id(self, client: AsyncClient) -> None:
        first = await client.get("/health")
        second = await client.get("/health")

        assert first.headers[REQUEST_ID_HEADER] != second.headers[REQUEST_ID_HEADER]

    async def test_request_id_appears_in_logs(
        self, client: AsyncClient, log_stream: io.StringIO
    ) -> None:
        response = await client.post("/projects", json={"name": "x"})
        request_id = response.headers[REQUEST_ID_HEADER]

        lines = [json.loads(line) for line in log_stream.getvalue().splitlines() if line]

        assert lines, "expected at least one log line"
        assert any(line.get("request_id") == request_id for line in lines)


@pytest.mark.security
class TestLogRedaction:
    async def test_credentials_never_reach_the_log(
        self, client: AsyncClient, log_stream: io.StringIO
    ) -> None:
        """The end-to-end guarantee, exercised through a real request."""
        await client.post(
            "/auth/register",
            json={
                "email": EMAIL,
                "password": PASSWORD,
                "display_name": "Ada Lovelace",
            },
        )

        output = log_stream.getvalue()

        assert PASSWORD not in output

    async def test_tokens_never_reach_the_log(
        self,
        client: AsyncClient,
        api,  # type: ignore[no-untyped-def]
        log_stream: io.StringIO,
    ) -> None:
        session = await api.register()
        await client.get("/auth/me", headers=api.auth_header(session))

        output = log_stream.getvalue()

        assert session["access_token"] not in output
        assert session["refresh_token"] not in output

    async def test_configured_secrets_are_registered_at_startup(self, client: AsyncClient) -> None:
        """Registration happens in the lifespan, before any request is served."""
        redactor = get_redactor()

        cleaned = redactor.redact_text("connecting to postgresql://test:test@localhost:5432/test")

        assert "postgresql://test:test@localhost:5432/test" not in cleaned


class TestOpenApi:
    async def test_schema_is_served(self, client: AsyncClient) -> None:
        response = await client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert schema["info"]["title"] == "AI Software Factory API"
        assert "/auth/register" in schema["paths"]
        assert "/projects/{project_id}" in schema["paths"]

    async def test_error_envelope_is_documented(self, client: AsyncClient) -> None:
        """Clients generate types from this; the error shape must be in it."""
        schema = (await client.get("/openapi.json")).json()

        assert "ErrorResponse" in schema["components"]["schemas"]

    @pytest.mark.security
    async def test_schema_contains_no_secrets(self, client: AsyncClient) -> None:
        raw = (await client.get("/openapi.json")).text

        assert "postgresql://" not in raw
        assert "test-secret-key" not in raw
