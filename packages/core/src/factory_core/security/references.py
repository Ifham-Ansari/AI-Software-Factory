"""Secret references and the sinks allowed to resolve them.

Agents and graph state never carry a secret *value*. They carry a reference:

    secret://project/{project_id}/{NAME}

A reference is inert. Turning one into a value requires the resolver, and the resolver
demands two things the reference itself cannot supply: a declared **sink** from a fixed
allowlist, and a context that is not being traced.

Why a sink allowlist rather than a permission flag: there are exactly three places in this
system where a plaintext credential is legitimately needed — injecting provider
environment variables, opening a migration connection, and populating a sandbox
environment. Enumerating them means a fourth call site cannot be added without editing
this file, which is a reviewable event.

The traced-context refusal matters because Phase 3 sends prompts and tool I/O to LangSmith.
A resolution inside a traced span would put the plaintext one serialisation away from a
third party. Redaction is the second line of defence; refusing to resolve there at all is
the first.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from enum import StrEnum

from factory_core.errors import AppError, ErrorCode

#: Scheme prefix for every reference this system understands. Not a credential -- it
#: is the literal URI scheme, which is why the hardcoded-password check is silenced.
SECRET_SCHEME = "secret://"  # noqa: S105

#: Secret names are environment-variable shaped: uppercase, digits, underscore.
_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")

_REFERENCE_PATTERN = re.compile(
    r"^secret://project/(?P<project_id>[0-9a-fA-F-]{36})/(?P<name>[A-Z][A-Z0-9_]{0,63})$"
)

#: True while execution is inside a span whose inputs/outputs are shipped to a tracer.
_traced: ContextVar[bool] = ContextVar("secret_traced_context", default=False)


class SecretSink(StrEnum):
    """The only places a secret value may legitimately be resolved.

    Adding a member is a security decision. Each one corresponds to a boundary where a
    plaintext credential is genuinely unavoidable, and each is audited on every use.
    """

    #: Environment variables handed to a deployment provider.
    PROVIDER_ENV = "provider_env"
    #: Connection string used to apply a database migration.
    MIGRATION_CONNECTION = "migration_connection"
    #: Environment inside the generated-code sandbox container.
    SANDBOX_ENV = "sandbox_env"


class InvalidSecretReferenceError(AppError):
    """A string was not a well-formed ``secret://`` reference."""

    code = ErrorCode.VALIDATION_FAILED
    status_code = 400
    message = "That is not a valid secret reference."


class SinkNotAllowedError(AppError):
    """Resolution was attempted from a sink that is not on the allowlist."""

    code = ErrorCode.FORBIDDEN
    status_code = 403
    message = "Secret resolution is not permitted from this sink."


class TracedContextError(AppError):
    """Resolution was attempted inside a traced span.

    Raised rather than silently redacting, because a caller that wants a plaintext
    credential inside a trace has a design problem, not a formatting problem.
    """

    code = ErrorCode.FORBIDDEN
    status_code = 403
    message = "Secrets cannot be resolved inside a traced context."


@dataclass(frozen=True, slots=True)
class SecretReference:
    """A pointer to a secret, safe to place in logs, state and prompts."""

    project_id: str
    name: str

    def __str__(self) -> str:
        return f"{SECRET_SCHEME}project/{self.project_id}/{self.name}"

    @classmethod
    def parse(cls, raw: str) -> SecretReference:
        """Parse a reference string.

        Raises:
            InvalidSecretReferenceError: The string is not a well-formed reference. The
                message deliberately does not echo the input — a malformed reference can
                arrive from an LLM and echoing it back into an error body is a small
                injection surface for no benefit.
        """
        match = _REFERENCE_PATTERN.match(raw.strip()) if isinstance(raw, str) else None
        if match is None:
            raise InvalidSecretReferenceError
        return cls(project_id=match.group("project_id"), name=match.group("name"))

    @classmethod
    def build(cls, project_id: str, name: str) -> SecretReference:
        """Build a reference, validating the name shape.

        Raises:
            InvalidSecretReferenceError: The name is not environment-variable shaped.
        """
        if not _NAME_PATTERN.match(name):
            raise InvalidSecretReferenceError(
                "Secret names must be uppercase letters, digits and underscores."
            )
        return cls(project_id=str(project_id), name=name)


def is_secret_reference(value: object) -> bool:
    """Whether a value looks like a secret reference.

    Used to spot references in structures that should hold values, and values in
    structures that should hold references.
    """
    return isinstance(value, str) and value.startswith(SECRET_SCHEME)


def is_valid_secret_name(name: str) -> bool:
    """Whether a name is acceptable for a stored secret."""
    return bool(_NAME_PATTERN.match(name))


def in_traced_context() -> bool:
    """Whether execution is currently inside a traced span."""
    return _traced.get()


@contextmanager
def traced_context() -> Iterator[None]:
    """Mark the enclosing block as traced, forbidding secret resolution within it.

    Phase 3 wraps every model and tool invocation in this. It exists now so that the
    refusal is testable and so the resolver's guard is never dead code.
    """
    token = _traced.set(True)
    try:
        yield
    finally:
        _traced.reset(token)


def ensure_resolvable(sink: SecretSink) -> None:
    """Assert that a resolution from ``sink`` is permitted right now.

    Raises:
        SinkNotAllowedError: ``sink`` is not a recognised sink.
        TracedContextError: Execution is inside a traced span.
    """
    if not isinstance(sink, SecretSink):
        raise SinkNotAllowedError
    if in_traced_context():
        raise TracedContextError
