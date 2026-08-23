"""Deployment environments and the guarantees each one implies."""

from __future__ import annotations

from enum import StrEnum


class Environment(StrEnum):
    """Where this process is running.

    The value drives safety defaults: production refuses conveniences that are fine
    locally (permissive CORS, weak secrets, verbose error bodies).
    """

    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production(self) -> bool:
        """True when running against real user data."""
        return self is Environment.PRODUCTION

    @property
    def is_deployed(self) -> bool:
        """True for any shared environment (as opposed to a developer machine)."""
        return self in (Environment.STAGING, Environment.PRODUCTION)

    @property
    def allows_debug_detail(self) -> bool:
        """Whether error responses may carry internal diagnostic detail."""
        return self in (Environment.DEVELOPMENT, Environment.TEST)
