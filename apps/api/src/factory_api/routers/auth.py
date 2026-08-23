"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import SecretStr

from factory_api.dependencies import AuthServiceDep, CurrentUser
from factory_api.schemas import (
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    SessionResponse,
    SignInRequest,
    SignOutRequest,
    UserResponse,
)
from factory_api.schemas.errors import ErrorResponse
from factory_core.application.auth import RegisterCommand, SignInCommand

router = APIRouter(prefix="/auth", tags=["auth"])

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
}


@router.post(
    "/register",
    response_model=SessionResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_ERRORS,
    summary="Create an account",
)
async def register(body: RegisterRequest, service: AuthServiceDep) -> SessionResponse:
    """Register a new account and return a session.

    Registration signs the user straight in. Requiring a separate sign-in immediately
    after would add a round trip and a second chance to mistype the password, for no
    security benefit — the credentials were just verified.
    """
    session = await service.register(
        RegisterCommand(
            email=body.email,
            password=SecretStr(body.password),
            display_name=body.display_name,
        )
    )
    return SessionResponse.from_session(session)


@router.post(
    "/sign-in",
    response_model=SessionResponse,
    responses=_ERRORS,
    summary="Authenticate",
)
async def sign_in(body: SignInRequest, service: AuthServiceDep) -> SessionResponse:
    """Exchange credentials for a session.

    An unknown email and a wrong password produce the same error, after the same amount
    of work, so this endpoint cannot be used to discover which addresses are registered.
    """
    session = await service.sign_in(
        SignInCommand(email=body.email, password=SecretStr(body.password))
    )
    return SessionResponse.from_session(session)


@router.post(
    "/refresh",
    response_model=SessionResponse,
    responses=_ERRORS,
    summary="Refresh a session",
)
async def refresh(body: RefreshRequest, service: AuthServiceDep) -> SessionResponse:
    """Exchange a refresh token for a new session.

    The presented token is consumed: a successor is issued and the old one is retired.
    Presenting a retired token is treated as theft and revokes the whole session family.
    """
    session = await service.refresh(body.refresh_token)
    return SessionResponse.from_session(session)


@router.post(
    "/sign-out",
    response_model=MessageResponse,
    responses=_ERRORS,
    summary="Revoke a session",
)
async def sign_out(body: SignOutRequest, service: AuthServiceDep) -> MessageResponse:
    """Revoke a refresh token.

    Idempotent, and deliberately indistinguishable for a token that never existed:
    reporting the difference would tell an unauthenticated caller whether a token is real.
    """
    await service.sign_out(body.refresh_token)
    return MessageResponse(message="Signed out.")


@router.get(
    "/me",
    response_model=UserResponse,
    responses={401: {"model": ErrorResponse}},
    summary="Current user",
)
async def me(user: CurrentUser) -> UserResponse:
    """Return the authenticated user."""
    return UserResponse.from_entity(user)
