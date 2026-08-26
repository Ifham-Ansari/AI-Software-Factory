"""Authorization policies.

Authorization decisions live here, not in routers and not in services, so there is one
place to read to know who may do what — and one place to test.

The central rule of this system is project isolation: a project belongs to exactly one
user, and no other user may read it, modify it, or learn that it exists.
"""

from __future__ import annotations

from factory_core.domain.entities import Project, User
from factory_core.domain.ids import UserId
from factory_core.errors import AuthorizationError, NotFoundError, ValidationError


def can_access_project(actor_id: UserId, project: Project) -> bool:
    """Whether this actor may read the given project."""
    return project.owner_id == actor_id


def ensure_can_access_project(actor_id: UserId, project: Project | None) -> Project:
    """Return the project if this actor may access it, otherwise raise ``NotFoundError``.

    Raising *not found* rather than *forbidden* for someone else's project is deliberate.
    A 403 confirms that the identifier is real, which turns the endpoint into an oracle
    for enumerating other users' projects. Both cases must be indistinguishable.

    Args:
        actor_id: The authenticated user making the request.
        project: The project loaded from storage, or ``None`` when no row matched.

    Returns:
        The project, guaranteed to be owned by ``actor_id``.

    Raises:
        NotFoundError: The project does not exist, or belongs to someone else.
    """
    if project is None or not can_access_project(actor_id, project):
        raise NotFoundError("The requested project was not found.")
    return project


def ensure_can_modify_project(actor_id: UserId, project: Project | None) -> Project:
    """Return the project if this actor may modify it.

    Raises:
        NotFoundError: The project does not exist, or belongs to someone else.
        AuthorizationError: The project is archived and therefore read-only.
    """
    accessible = ensure_can_access_project(actor_id, project)
    if accessible.is_archived:
        raise AuthorizationError("An archived project cannot be modified.")
    return accessible


def ensure_can_restore_project(actor_id: UserId, project: Project | None) -> Project:
    """Return the project if this actor may take it out of the archive.

    Deliberately *not* built on :func:`ensure_can_modify_project`, which refuses archived
    projects. Restoring is the single change an archived project has to accept: if every
    write is blocked, archiving is a one-way trip and the only way back is deletion — which
    is exactly the trap this pair of functions exists to avoid.

    Ownership is still enforced, and restoring something that is not archived is rejected
    rather than treated as a no-op, so a confused caller hears about it.

    Raises:
        NotFoundError: The project does not exist, or belongs to someone else.
        ValidationError: The project is not archived, so there is nothing to restore.
    """
    accessible = ensure_can_access_project(actor_id, project)
    if not accessible.is_archived:
        raise ValidationError("This project is not archived.")
    return accessible


def ensure_active_user(user: User) -> User:
    """Return the user if the account may act, otherwise raise.

    Raises:
        AuthorizationError: The account is suspended.
    """
    if not user.is_active:
        raise AuthorizationError("This account is not permitted to sign in.")
    return user
