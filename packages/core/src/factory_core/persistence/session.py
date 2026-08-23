"""Session management and the unit of work.

A unit of work is one transaction. It commits if the block completes and rolls back if
anything raises, so a handler cannot half-apply a change by forgetting to commit on one
branch.

Operational errors are translated here rather than at the API boundary. Everything above
this layer should be able to catch ``DatabaseUnavailableError`` without importing
SQLAlchemy — that is what keeps the application layer free of persistence detail.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from factory_core.errors import AlreadyExistsError, DatabaseUnavailableError

SessionFactory = async_sessionmaker[AsyncSession]


def create_session_factory(engine: AsyncEngine) -> SessionFactory:
    """Build a session factory bound to an engine.

    ``expire_on_commit=False`` keeps attributes readable after commit. Without it, reading
    any field of a just-committed row triggers a lazy refresh, which in async code raises
    ``MissingGreenlet`` rather than doing the obvious thing.
    """
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def unit_of_work(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Run a block inside a single transaction.

    Commits on success, rolls back on any exception, and always closes the session.

    Raises:
        AlreadyExistsError: A uniqueness constraint was violated.
        DatabaseUnavailableError: The database could not be reached.
    """
    session = factory()
    try:
        yield session
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _translate_integrity_error(exc) from exc
    except (OperationalError, DBAPIError) as exc:
        await session.rollback()
        raise DatabaseUnavailableError from exc
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


@asynccontextmanager
async def read_only_session(factory: SessionFactory) -> AsyncIterator[AsyncSession]:
    """Run a read-only block, rolling back rather than committing.

    Using this for queries makes an accidental write in a GET handler impossible to
    persist, and documents intent at the call site.
    """
    session = factory()
    try:
        yield session
    except (OperationalError, DBAPIError) as exc:
        raise DatabaseUnavailableError from exc
    finally:
        await session.rollback()
        await session.close()


def _translate_integrity_error(exc: IntegrityError) -> Exception:
    """Map a constraint violation onto a typed application error.

    The constraint name is matched rather than the driver message because names are
    stable (see the naming convention in ``base.py``) while message text is not.
    """
    constraint = _constraint_name(exc)
    if constraint == "uq_users_email":
        return AlreadyExistsError("An account with that email address already exists.")
    if constraint == "uq_projects_owner_id_slug":
        return AlreadyExistsError("You already have a project with that name.")
    if constraint == "uq_refresh_tokens_token_hash":
        return AlreadyExistsError("That token has already been issued.")
    return AlreadyExistsError("The resource already exists.")


def _constraint_name(exc: IntegrityError) -> str | None:
    """Extract the violated constraint's name from a driver error, if available."""
    original = getattr(exc, "orig", None)
    diagnostic = getattr(original, "diag", None)
    name = getattr(diagnostic, "constraint_name", None)
    return str(name) if name else None
