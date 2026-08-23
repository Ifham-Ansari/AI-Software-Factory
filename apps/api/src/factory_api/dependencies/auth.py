"""Authentication and authorization dependencies.

``CurrentUser`` is the authorization boundary. A route that declares it is authenticated;
a route that does not is public. There is no middleware that authenticates "most" routes,
because that pattern makes it invisible which routes were accidentally left open.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from factory_api.dependencies.context import StateDep
from factory_api.dependencies.repositories import UserRepositoryDep
from factory_core.domain.entities import User
from factory_core.domain.ids import UserId
from factory_core.domain.policies import ensure_active_user
from factory_core.errors import AuthenticationError
from factory_core.observability import bind_context

# auto_error=False so a missing header raises our typed error with the standard envelope,
# rather than FastAPI's own 403 with a different body shape.
_bearer = HTTPBearer(auto_error=False, description="Access token issued by /auth/sign-in")


async def get_current_user(
    state: StateDep,
    users: UserRepositoryDep,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer)],
) -> AsyncIterator[User]:
    """Resolve the authenticated user from the Authorization header.

    Yields rather than returns so the ``user_id`` logging binding stays in scope for the
    whole request. A plain ``return`` would tear the context down before the route
    handler even runs, and every log line it produced would be missing the user.

    Raises:
        AuthenticationError: No credentials were supplied.
        TokenExpiredError: The access token has expired.
        TokenInvalidError: The token is malformed, forged, or names an unknown subject.
        AuthorizationError: The account is suspended.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError

    claims = state.issuer.verify(credentials.credentials)
    subject = claims.user_id
    if subject is None:
        raise AuthenticationError

    user = await users.get_by_id(subject)
    if user is None:
        # The token signature is valid but the account is gone. Treat it as unauthenticated
        # rather than "not found": the caller has no session either way.
        raise AuthenticationError

    active = ensure_active_user(user)
    with bind_context(user_id=str(active.id)):
        yield active


async def get_current_user_id(
    user: Annotated[User, Depends(get_current_user)],
) -> UserId:
    """Resolve just the authenticated user's identifier."""
    return user.id


CurrentUser = Annotated[User, Depends(get_current_user)]
CurrentUserId = Annotated[UserId, Depends(get_current_user_id)]
