"""Process-level runtime setup.

One concern lives here: selecting an asyncio event loop that the database driver can use.

Since Python 3.8, Windows defaults to ``ProactorEventLoop``. psycopg's async mode does not
support it and raises at the first connection attempt:

    Psycopg cannot use the 'ProactorEventLoop' to run in async mode.

psycopg is the only PostgreSQL driver in this system (architecture.md §15), so every
process that touches the database must run on a ``SelectorEventLoop``. Getting this wrong
produces a failure that looks like a connectivity problem and costs an afternoon.

Two mechanisms are needed, because two different things create loops:

* :func:`configure_event_loop` sets the *policy*, which covers anything calling
  ``asyncio.run()`` or ``asyncio.new_event_loop()`` — the worker, and pytest-asyncio.
* :func:`event_loop_factory` returns an explicit loop factory, needed because uvicorn
  ignores the policy: it hard-codes ``ProactorEventLoop`` on Windows via its own factory.
  Setting the policy alone leaves the API server broken while every test passes.

Both are no-ops off Windows, where the default selector loop is already correct.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable


def configure_event_loop() -> None:
    """Select an event loop policy compatible with the database driver.

    Covers code paths that create a loop through the policy — ``asyncio.run()`` and
    pytest-asyncio. Not sufficient for uvicorn; see :func:`event_loop_factory`.

    A no-op everywhere except Windows. Safe to call more than once.
    """
    # Guarded by a positive `== "win32"` check rather than an early return, for the same
    # reason as event_loop_factory below: mypy narrows sys.platform to the *checking*
    # host, so `if sys.platform != "win32": return` makes everything after it unreachable
    # when the check runs on Linux — which is what CI does. A platform-guarded block is
    # skipped silently instead of reported.
    if sys.platform == "win32":
        policy = getattr(asyncio, "WindowsSelectorEventLoopPolicy", None)
        if policy is not None:
            asyncio.set_event_loop_policy(policy())


def event_loop_factory() -> Callable[[], asyncio.AbstractEventLoop] | None:
    """Return a loop factory the database driver can use.

    Returns:
        ``asyncio.SelectorEventLoop`` on Windows; ``None`` elsewhere, meaning "the default
        loop is fine". ``None`` is accepted directly by ``asyncio.run(loop_factory=...)``,
        so callers need no platform check of their own.
    """
    # Assigned rather than returned from inside the branch: mypy narrows sys.platform to
    # the checking host, and an early return would make the other path "unreachable".
    factory: Callable[[], asyncio.AbstractEventLoop] | None = None
    if sys.platform == "win32":
        factory = asyncio.SelectorEventLoop
    return factory
