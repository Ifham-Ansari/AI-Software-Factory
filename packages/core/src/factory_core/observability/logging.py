"""Structured logging configuration.

Every log line is a JSON object carrying the correlation identifiers bound for the
current unit of work, and every line passes through redaction before it is emitted.

structlog is wired through the standard library rather than alongside it. One handler
renders everything, so output from third-party libraries (uvicorn, SQLAlchemy) is
formatted identically and — critically — cannot bypass redaction.

Processor order is not arbitrary:

    contextvars → correlation → level/name/timestamp → exception → redaction → render

Redaction runs last among value-producing processors so it sees everything earlier ones
added, including formatted exception tracebacks. A traceback is one of the most common
ways for a connection string to reach a log file.
"""

from __future__ import annotations

import logging
import sys
from typing import IO, Any, Literal

import structlog

from factory_core.observability.context import context_processor
from factory_core.observability.redaction import redaction_processor

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]
LogFormat = Literal["json", "console"]

_configured = False


def _service_binder(service_name: str) -> Any:
    """Build a processor that stamps the service name onto every event."""

    def bind_service(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
        event_dict.setdefault("service", service_name)
        return event_dict

    return bind_service


def configure_logging(
    *,
    level: LogLevel = "INFO",
    log_format: LogFormat = "json",
    service_name: str = "factory",
    stream: IO[str] | None = None,
) -> None:
    """Configure structlog and route the standard library through it.

    Safe to call more than once; later calls reconfigure rather than stacking handlers.

    Args:
        level: Minimum level to emit.
        log_format: ``json`` for machine consumption, ``console`` for local readability.
        service_name: Value bound to every event as ``service``.
        stream: Destination stream. Defaults to stdout; tests inject a buffer.
    """
    global _configured

    numeric_level = getattr(logging, level)

    shared: list[Any] = [
        structlog.contextvars.merge_contextvars,
        context_processor,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        _service_binder(service_name),
        redaction_processor,
    ]

    renderer: Any = (
        structlog.processors.JSONRenderer()
        if log_format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )

    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared,
    )
    handler = logging.StreamHandler(stream if stream is not None else sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(numeric_level)

    # Let uvicorn's loggers propagate to the root handler instead of writing directly.
    for noisy in ("uvicorn", "uvicorn.error", "uvicorn.access", "sqlalchemy.engine"):
        stdlib_logger = logging.getLogger(noisy)
        stdlib_logger.handlers = []
        stdlib_logger.propagate = True

    _configured = True


def is_configured() -> bool:
    """Whether logging has been configured in this process."""
    return _configured


def get_logger(name: str | None = None) -> Any:
    """Return a bound structured logger.

    Args:
        name: Logger name, conventionally ``__name__`` of the calling module.
    """
    return structlog.get_logger(name)
