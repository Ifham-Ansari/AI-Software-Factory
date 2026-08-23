"""Authentication endpoints.

Registration does not return a session. An account is created unverified, a one-time code
is emailed, and tokens are issued only once that code is redeemed — otherwise anyone could
sign up with an address they do not control and immediately use the account.

    POST /auth/register            -> 202, code sent
    POST /auth/verify-email        -> 200, session
    POST /auth/resend-verification -> 202, code sent (or pretends to)
"""

from __future__ import annotations

from fastapi import APIRouter, status
from pydantic import SecretStr

from factory_api.dependencies import (
    AuthServiceDep,
    CurrentUser,
    StateDep,
    UserRepositoryDep,
    VerificationServiceDep,
)
from factory_api.schemas import (
    MessageResponse,
    RefreshRequest,
    RegisterRequest,
    ResendVerificationRequest,
    SessionResponse,
    SignInRequest,
    SignOutRequest,
    UserResponse,
    VerificationChallengeResponse,
    VerifyEmailRequest,
)
from factory_api.schemas.errors import ErrorResponse
from factory_core.application.auth import RegisterCommand, SignInCommand
from factory_core.errors import InvalidCredentialsError

router = APIRouter(prefix="/auth", tags=["auth"])

_ERRORS: dict[int | str, dict[str, object]] = {
    400: {"model": ErrorResponse},
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse},
    422: {"model": ErrorResponse},
    429: {"model": ErrorResponse},
}


@router.post(
    "/register",
    response_model=VerificationChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Create an account and send a verification code",
)
async def register(
    body: RegisterRequest,
    service: AuthServiceDep,
    verification: VerificationServiceDep,
) -> VerificationChallengeResponse:
    """Create an unverified account and email a one-time code.

    202 rather than 201: the account exists but is not yet usable, and the meaningful work
    — proving the address — has not finished.

    The daily cap is not applied to this first code. The user has not asked for anything
    yet, so refusing their very first code would be nonsensical.
    """
    user = await service.register(
        RegisterCommand(
            email=body.email,
            password=SecretStr(body.password),
            display_name=body.display_name,
        )
    )
    challenge = await verification.issue(user, enforce_limits=False)
    return VerificationChallengeResponse(
        email=challenge.email,
        expires_in=challenge.expires_in_seconds,
        resend_available_in=challenge.resend_available_in_seconds,
    )


@router.post(
    "/verify-email",
    response_model=SessionResponse,
    responses=_ERRORS,
    summary="Redeem a verification code",
)
async def verify_email(
    body: VerifyEmailRequest,
    service: AuthServiceDep,
    verification: VerificationServiceDep,
    users: UserRepositoryDep,
) -> SessionResponse:
    """Redeem a code and start a session.

    An unknown address produces the same error as a wrong code, so this endpoint cannot be
    used to discover which addresses are registered. Redeeming a code proves ownership of
    the address, so a session is issued without re-checking the password.
    """
    user = await users.get_by_email(body.email)
    if user is None:
        raise InvalidCredentialsError("That code is not valid.")

    verified = await verification.verify(user, body.code)
    return SessionResponse.from_session(await service.start_session(verified))


@router.post(
    "/resend-verification",
    response_model=VerificationChallengeResponse,
    status_code=status.HTTP_202_ACCEPTED,
    responses=_ERRORS,
    summary="Send a fresh verification code",
)
async def resend_verification(
    body: ResendVerificationRequest,
    verification: VerificationServiceDep,
    users: UserRepositoryDep,
    state: StateDep,
) -> VerificationChallengeResponse:
    """Issue a new code, superseding any previous one.

    Answers identically for an unknown address and an already-verified one. Anything else
    would turn this unauthenticated endpoint into an account-existence oracle. Rate limits
    still apply to real accounts, so it cannot be used to flood an inbox.
    """
    user = await users.get_by_email(body.email)

    if user is not None and not user.is_email_verified:
        challenge = await verification.issue(user)
        return VerificationChallengeResponse(
            email=challenge.email,
            expires_in=challenge.expires_in_seconds,
            resend_available_in=challenge.resend_available_in_seconds,
        )

    # No account, or already verified: report the identical shape without sending
    # anything. The values come from the same settings the real path uses — a decoy that
    # differed by even one number would be exactly the signal this is hiding.
    policy = state.settings.verification
    return VerificationChallengeResponse(
        email=body.email,
        expires_in=policy.ttl_seconds,
        resend_available_in=policy.resend_cooldown_seconds,
    )


@router.post(
    "/sign-in",
    response_model=SessionResponse,
    responses=_ERRORS,
    summary="Authenticate",
)
async def sign_in(body: SignInRequest, service: AuthServiceDep) -> SessionResponse:
    """Exchange credentials for a session.

    An unknown email and a wrong password produce the same error, after the same amount of
    work, so this endpoint cannot be used to discover which addresses are registered.

    Correct credentials on an unverified account return ``email_not_verified`` (403). That
    only ever reaches someone who already knows the password, so it is not an enumeration
    vector — and the caller needs to know to go and enter their code.
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
