"""Session-wide test configuration.

Applies the same event loop policy the application entrypoints use. Without it, any test
that opens a real database connection fails on Windows with a psycopg error about
``ProactorEventLoop`` rather than the thing it was actually testing.
"""

from __future__ import annotations

from factory_core.runtime import configure_event_loop

configure_event_loop()
