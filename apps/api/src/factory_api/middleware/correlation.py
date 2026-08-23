"""Request correlation and access logging.

Binds a request id before anything else runs, so every log line produced anywhere
underneath — including inside exception handlers — carries it without being passed
explicitly.

An inbound ``X-Request-ID`` is honoured so a trace can span a reverse proxy or a calling
service, but it is validated first: the value ends up in log fields and response headers,
and an unvalidated one is a log-injection and header-splitting vector.
"""

from __future__ import annotations

import re
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from factory_core.observability import bind_context, get_logger, new_request_id

logger = get_logger(__name__)

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LENGTH = 64
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

# Paths excluded from access logging. Orchestrator probes hit these every few seconds and
# would otherwise bury real traffic.
_QUIET_PATHS = frozenset({"/health", "/ready"})


class CorrelationMiddleware(BaseHTTPMiddleware):
    """Assigns a request id, binds logging context, and logs the outcome."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Wrap one request."""
        request_id = self._resolve_request_id(request)
        started = time.perf_counter()

        with bind_context(request_id=request_id):
            request.state.request_id = request_id
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            response.headers[REQUEST_ID_HEADER] = request_id

            if request.url.path not in _QUIET_PATHS:
                logger.info(
                    "request.completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            return response

    @staticmethod
    def _resolve_request_id(request: Request) -> str:
        """Honour a valid inbound request id, otherwise mint one.

        A caller-supplied value is echoed in a response header and written to logs, so
        anything that is not a short alphanumeric token is discarded rather than
        sanitised — there is no legitimate request id that needs escaping.
        """
        supplied = request.headers.get(REQUEST_ID_HEADER)
        if supplied and _SAFE_REQUEST_ID.match(supplied):
            return supplied
        return new_request_id()
