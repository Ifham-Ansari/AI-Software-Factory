"""Re-wrap every project DEK under the active master key.

    uv run python scripts/rotate_master_key.py [--dry-run]

Step 3 of the rotation procedure in ``docs/runbooks/key-management.md``. Run it after
deploying the new key as active with the old one in ``SECRETS__PREVIOUS_KEYS``.

**Idempotent and resumable.** It re-wraps only rows whose ``key_version`` is not the
active one, and commits per project, so interrupting it and re-running is safe. It never
touches a DEK's *material* — only the key it is wrapped with — so the values that DEK
encrypts stay readable throughout.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from factory_core.config import load_settings
from factory_core.persistence import (
    create_engine,
    create_session_factory,
    dispose_engine,
    unit_of_work,
)
from factory_core.persistence.models_secrets import ProjectKeyRow
from factory_core.runtime import configure_event_loop
from factory_core.security.envelope import DecryptionError
from factory_core.security.keyring import KeyRing, build_keyring


async def _rotate(keyring: KeyRing, *, dry_run: bool) -> int:
    """Re-wrap outdated DEKs. Returns a process exit code."""
    settings = load_settings()
    engine = create_engine(settings.database, application_name="key-rotation")
    session_factory = create_session_factory(engine)

    rewrapped = 0
    already_current = 0
    failed: list[str] = []

    try:
        async with unit_of_work(session_factory) as session:
            rows = (await session.execute(select(ProjectKeyRow))).scalars().all()
            targets = [row.project_id for row in rows if row.key_version != keyring.active_version]
            already_current = len(rows) - len(targets)

        print(f"active key version : {keyring.active_version}")  # noqa: T201
        print(f"already current    : {already_current}")  # noqa: T201
        print(f"needing re-wrap    : {len(targets)}")  # noqa: T201

        if dry_run:
            print("\ndry run: nothing was modified")  # noqa: T201
            return 0

        for project_id in targets:
            # One transaction per project so an interruption leaves a consistent state
            # and a re-run resumes rather than restarting.
            try:
                async with unit_of_work(session_factory) as session:
                    statement = select(ProjectKeyRow).where(ProjectKeyRow.project_id == project_id)
                    row = (await session.execute(statement)).scalar_one_or_none()
                    if row is None or row.key_version == keyring.active_version:
                        continue
                    row.wrapped_dek = keyring.rewrap_dek(
                        row.wrapped_dek, project_id=str(project_id)
                    )
                    row.key_version = keyring.active_version
                rewrapped += 1
            except DecryptionError:
                # The wrapping key is not in configuration. Naming the project lets an
                # operator restore the right retired key and re-run.
                failed.append(str(project_id))

        print(f"\nre-wrapped         : {rewrapped}")  # noqa: T201
        if failed:
            print(f"FAILED             : {len(failed)}")  # noqa: T201
            for failed_id in failed:
                print(f"  {failed_id}")  # noqa: T201
            print(  # noqa: T201
                "\nThese DEKs were wrapped with a key that is not in SECRETS__MASTER_KEY "
                "or SECRETS__PREVIOUS_KEYS. Restore it and re-run."
            )
            return 1
    finally:
        await dispose_engine(engine)

    print("\nRotation complete. Verify with:")  # noqa: T201
    print("  SELECT key_version, count(*) FROM project_keys GROUP BY key_version;")  # noqa: T201
    return 0


def main() -> int:
    """Entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would be re-wrapped without modifying anything.",
    )
    args = parser.parse_args()

    settings = load_settings()
    if not settings.secrets.is_configured:
        print("error: SECRETS__MASTER_KEY is not configured", file=sys.stderr)  # noqa: T201
        return 2

    keyring = build_keyring(settings.secrets)
    configure_event_loop()
    return asyncio.run(_rotate(keyring, dry_run=bool(args.dry_run)))


if __name__ == "__main__":
    sys.exit(main())
