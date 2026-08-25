"""Generate a master key (KEK) for envelope encryption.

    uv run python scripts/generate_master_key.py [--version v1]

Prints one line ready to paste into ``.env``. The key is printed to stdout and never
written anywhere — piping it into a file is the caller's decision, and an accidental
`>> .env.example` is exactly the mistake this avoids automating.

Losing a KEK makes every secret it wraps permanently unrecoverable. Back it up before
using it for anything real; see docs/runbooks/key-management.md.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys

KEY_LENGTH_BYTES = 32


def main() -> int:
    """Print a fresh versioned master key."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--version",
        default="v1",
        help="Key version label. Increment when rotating (v1 -> v2).",
    )
    args = parser.parse_args()

    version = str(args.version).strip()
    if not version or ":" in version:
        print("error: --version must be non-empty and must not contain ':'", file=sys.stderr)  # noqa: T201
        return 2

    material = base64.b64encode(os.urandom(KEY_LENGTH_BYTES)).decode("ascii")
    print(f"SECRETS__MASTER_KEY={version}:{material}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
