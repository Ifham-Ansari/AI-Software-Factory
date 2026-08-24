"""Test-only introspection endpoints.

``build_debug_router`` is called from ``create_app`` only when the resolved environment is
not deployed (development or test). Nothing here is reachable in staging or production —
the router itself is never registered, on top of the console email transport already
refusing to start there. It exists because e2e tests drive a real browser through a real
signup flow and have no other way to read a code that, by design, the API never returns.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from factory_api.dependencies import EmailSenderDep, UserRepositoryDep
from factory_api.schemas import VerificationCodeDebugResponse
from factory_core.infrastructure.email import ConsoleEmailSender, extract_code


def build_debug_router() -> APIRouter:
    """Build the debug router. Only called for non-deployed environments."""
    router = APIRouter(prefix="/debug", tags=["debug"])

    @router.get(
        "/verification-code",
        response_model=VerificationCodeDebugResponse,
        summary="Read the last verification code sent to an address (dev/test only)",
    )
    async def last_verification_code(
        email: str,
        users: UserRepositoryDep,
        sender: EmailSenderDep,
    ) -> VerificationCodeDebugResponse:
        user = await users.get_by_email(email)
        if user is None or not isinstance(sender, ConsoleEmailSender):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "No code available.")

        for message in reversed(sender.sent):
            if message.to != email:
                continue
            code = extract_code(message.text_body)
            if code is not None:
                return VerificationCodeDebugResponse(email=email, code=code)

        raise HTTPException(status.HTTP_404_NOT_FOUND, "No code available.")

    return router
