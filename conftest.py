"""Session-wide test configuration.

Two things happen before any test is collected.

**Event loop policy.** The same one the application entrypoints use. Without it, any test
that opens a real database connection fails on Windows with a psycopg error about
``ProactorEventLoop`` rather than the thing it was actually testing.

**``.env`` loading.** ``TEST_DATABASE_URL`` gates the integration suite, and the
documentation tells developers to put it in ``.env``. Pydantic Settings reads that file
when building ``Settings``, but it never reaches ``os.environ`` — so without this, the
documented workflow would silently leave 37 tests skipped and look like everything passed.
Existing environment variables win, so CI (which sets them directly) is unaffected.
"""

from __future__ import annotations

import os
from pathlib import Path

from factory_core.runtime import configure_event_loop

configure_event_loop()


def _load_dotenv() -> None:
    """Load ``.env`` into the process environment without overriding what is already set."""
    env_file = Path(__file__).parent / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_dotenv()
