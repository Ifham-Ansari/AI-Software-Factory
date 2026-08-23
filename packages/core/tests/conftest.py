"""Shared fixtures for core tests."""

from __future__ import annotations

import io
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from factory_core.domain import (
    Project,
    ProjectStatus,
    User,
    UserStatus,
    new_project_id,
    new_user_id,
)
from factory_core.domain.ids import ProjectId, UserId
from factory_core.observability import configure_logging, get_redactor
from factory_core.security import AccessTokenIssuer, PasswordHasher

FIXED_TIME = datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC)


@pytest.fixture
def password_hasher() -> PasswordHasher:
    """A hasher with deliberately low cost, so tests stay fast.

    Production parameters are ~50 ms per hash; a suite with dozens of hashes would spend
    most of its time in Argon2 for no additional coverage.
    """
    return PasswordHasher(time_cost=1, memory_cost_kib=8192, parallelism=1)


@pytest.fixture
def token_issuer() -> AccessTokenIssuer:
    """An access-token issuer with test credentials."""
    return AccessTokenIssuer(
        secret_key="test-secret-key-that-is-long-enough-for-hs256",
        issuer="test-issuer",
        audience="test-audience",
        ttl_seconds=600,
    )


@pytest.fixture
def user_id() -> UserId:
    """A stable user identifier for a single test."""
    return new_user_id()


@pytest.fixture
def other_user_id() -> UserId:
    """A second user, used to prove isolation."""
    return new_user_id()


@pytest.fixture
def project_id() -> ProjectId:
    """A stable project identifier for a single test."""
    return new_project_id()


@pytest.fixture
def user(user_id: UserId) -> User:
    """An active user entity."""
    return User(
        id=user_id,
        email="ada@example.com",
        display_name="Ada Lovelace",
        status=UserStatus.ACTIVE,
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )


@pytest.fixture
def project(project_id: ProjectId, user_id: UserId) -> Project:
    """A draft project owned by ``user_id``."""
    return Project(
        id=project_id,
        owner_id=user_id,
        name="Restaurant System",
        slug="restaurant-system",
        description="A restaurant management system.",
        status=ProjectStatus.DRAFT,
        created_at=FIXED_TIME,
        updated_at=FIXED_TIME,
    )


@pytest.fixture
def log_stream() -> Iterator[io.StringIO]:
    """Capture structured log output for assertions.

    Resets the redactor afterwards so registered secrets cannot leak between tests.
    """
    buffer = io.StringIO()
    configure_logging(level="DEBUG", log_format="json", service_name="test", stream=buffer)
    yield buffer
    get_redactor().clear()
