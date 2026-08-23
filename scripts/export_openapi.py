"""Export the API's OpenAPI schema to a file.

The schema is the contract between backend and frontend. Exporting it to a committed file
means the TypeScript types can be regenerated deterministically — in CI, in a pre-commit
hook, or on a machine with no database — without booting the API.

CI regenerates and diffs. A drift failure means someone changed an endpoint without
regenerating the types, which is exactly the moment to catch it: the alternative is a
frontend that compiles against a contract the backend no longer honours.

Usage:
    uv run python scripts/export_openapi.py [--output openapi.json] [--check]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from factory_api.main import create_app
from factory_core.config import (
    ApiSettings,
    DatabaseSettings,
    Environment,
    ObservabilitySettings,
    SecuritySettings,
    Settings,
)

# Placeholder configuration. The schema depends only on route and model definitions, so
# nothing here needs to be real — and using real settings would risk baking a live
# hostname into a committed artefact.
_SCHEMA_SETTINGS = Settings(
    environment=Environment.TEST,
    database=DatabaseSettings(url="postgresql://schema:schema@localhost:5432/schema"),  # type: ignore[arg-type]
    security=SecuritySettings(
        jwt_secret_key="openapi-export-placeholder-key-32-chars-min",  # type: ignore[arg-type]  # noqa: S106
    ),
    observability=ObservabilitySettings(),
    api=ApiSettings(docs_enabled=True),
)


def build_schema() -> dict[str, object]:
    """Produce the OpenAPI document."""
    schema: dict[str, object] = create_app(_SCHEMA_SETTINGS).openapi()
    return schema


def main() -> int:
    """Write or verify the schema. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="openapi.json")
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail if the committed file differs, instead of rewriting it",
    )
    args = parser.parse_args()

    target = Path(args.output)
    # sort_keys makes the output stable: without it, a dictionary reordering shows up as
    # a spurious diff and CI's drift check becomes noise people learn to ignore.
    rendered = json.dumps(build_schema(), indent=2, sort_keys=True) + "\n"

    if args.check:
        if not target.exists():
            print(f"FAIL: {target} does not exist. Run scripts/export_openapi.py.")  # noqa: T201
            return 1
        if target.read_text(encoding="utf-8") != rendered:
            print(  # noqa: T201
                f"FAIL: {target} is out of date.\n"
                "The API changed without regenerating the schema. Run:\n"
                "  uv run python scripts/export_openapi.py\n"
                "  pnpm --filter @factory/contracts generate"
            )
            return 1
        print(f"OK: {target} matches the current API.")  # noqa: T201
        return 0

    target.write_text(rendered, encoding="utf-8")
    print(f"Wrote {target}")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
