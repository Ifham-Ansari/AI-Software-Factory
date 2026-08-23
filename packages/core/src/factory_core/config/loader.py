"""Settings loading with fail-fast, actionable errors.

A misconfigured process must not start. When it cannot start, the operator needs to know
*which* environment variable is wrong without reading a Pydantic traceback, so validation
errors are reformatted into environment-variable names.

Sections are constructed individually rather than letting the parent model build them.
Pydantic Settings does not populate a nested ``BaseSettings`` field from the environment
on the parent's behalf, so building each section explicitly is what makes both the
prefixed form (``DATABASE__POOL_SIZE``) and the conventional flat form (``DATABASE_URL``)
resolve — and it keeps every error attributable to a real variable name.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import ValidationError as PydanticValidationError
from pydantic_settings import BaseSettings

from factory_core.config.settings import (
    ApiSettings,
    DatabaseSettings,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)
from factory_core.errors import ConfigurationError

# Fields whose conventional flat env name differs from the prefixed path.
_FLAT_ALIASES: dict[str, str] = {
    "DATABASE__URL": "DATABASE_URL",
    "SECURITY__JWT_SECRET_KEY": "JWT_SECRET_KEY",
}


def _env_var_name(prefix: str, location: tuple[int | str, ...]) -> str:
    """Render a Pydantic error location as the environment variable that sets it.

    A field carrying an explicit ``validation_alias`` reports the alias as its location,
    and that alias already includes the section prefix. Prefixing again would produce
    ``DATABASE__DATABASE__URL``, so the prefix is only added when it is missing.
    """
    field = "__".join(str(part) for part in location if not isinstance(part, int)).upper()
    if not field:
        return prefix.rstrip("_")
    prefixed = field if field.startswith(prefix) else f"{prefix}{field}"
    return _FLAT_ALIASES.get(prefixed, prefixed)


def _collect(prefix: str, error: PydanticValidationError) -> list[str]:
    """Turn one section's validation error into operator-facing guidance."""
    lines: list[str] = []
    for item in error.errors():
        variable = _env_var_name(prefix, item["loc"])
        message = item["msg"].removeprefix("Value error, ")
        if not variable:
            # Model-level validators (cross-field rules) have no single variable.
            lines.append(f"  - {message}")
        elif item["type"] == "missing":
            lines.append(f"  - {variable} is required but was not set")
        else:
            lines.append(f"  - {variable}: {message}")
    return lines


def _build[SectionT: BaseSettings](
    section: type[SectionT], prefix: str, problems: list[str]
) -> SectionT | None:
    """Construct one settings section, recording problems instead of raising.

    Returning ``None`` on failure lets the loader report *every* misconfigured section at
    once. Failing on the first one would make fixing a fresh environment a slow guessing
    game of one variable per restart.
    """
    try:
        return section()  # values come from the environment, not from arguments
    except PydanticValidationError as exc:
        problems.extend(_collect(prefix, exc))
        return None


def load_settings() -> Settings:
    """Build settings from the environment, or raise ``ConfigurationError``.

    Raises:
        ConfigurationError: Configuration is missing or invalid. The message names every
            offending environment variable.
    """
    problems: list[str] = []
    database = _build(DatabaseSettings, "DATABASE__", problems)
    security = _build(SecuritySettings, "SECURITY__", problems)
    observability = _build(ObservabilitySettings, "OBSERVABILITY__", problems)
    api = _build(ApiSettings, "API__", problems)

    if problems:
        raise ConfigurationError(_format(problems))

    assert database is not None
    assert security is not None
    assert observability is not None
    assert api is not None

    try:
        return Settings(
            database=database,
            security=security,
            observability=observability,
            api=api,
        )
    except PydanticValidationError as exc:
        raise ConfigurationError(_format(_collect("", exc))) from exc


def _format(problems: list[str]) -> str:
    return "Invalid configuration. Fix the following and restart:\n" + "\n".join(problems)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings singleton.

    Cached because settings are immutable for the life of the process. Tests that need
    different configuration call ``get_settings.cache_clear()``.
    """
    return load_settings()
