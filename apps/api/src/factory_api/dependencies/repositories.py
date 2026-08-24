"""Repository providers.

Repositories are injected rather than constructed inside services so the database is a
single, replaceable seam. Tests override these providers and exercise every other layer —
routing, validation, token verification, service logic, error rendering — for real,
without a database.

Only the providers that need no authentication live here. The project repository is scoped
to the authenticated caller, so it is defined in ``services.py`` alongside the service that
uses it; putting it here would make this module import ``auth``, which already imports
``get_user_repository`` from this one.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from factory_api.dependencies.context import SessionDep
from factory_core.persistence import (
    AuditRepository,
    RefreshTokenRepository,
    UserRepository,
    VerificationRepository,
)


def get_user_repository(session: SessionDep) -> UserRepository:
    """Provide the user repository."""
    return UserRepository(session)


def get_refresh_token_repository(session: SessionDep) -> RefreshTokenRepository:
    """Provide the refresh-token repository."""
    return RefreshTokenRepository(session)


def get_audit_repository(session: SessionDep) -> AuditRepository:
    """Provide the audit repository."""
    return AuditRepository(session)


UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]
RefreshTokenRepositoryDep = Annotated[RefreshTokenRepository, Depends(get_refresh_token_repository)]


def get_verification_repository(session: SessionDep) -> VerificationRepository:
    """Provide the email-verification repository."""
    return VerificationRepository(session)


AuditRepositoryDep = Annotated[AuditRepository, Depends(get_audit_repository)]
VerificationRepositoryDep = Annotated[VerificationRepository, Depends(get_verification_repository)]
