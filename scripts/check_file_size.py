"""Enforce the 200-250 line source file limit.

The rule exists because a file that outgrows a screenful stops being one idea. Splitting
at the limit forces the question "what are the separate responsibilities here?" while the
answer is still cheap.

Exceptions are listed explicitly rather than being pattern-matched, so adding one is a
visible decision in a diff. Run with ``--list`` to see the largest files.

Usage:
    uv run python scripts/check_file_size.py [--limit N] [--warn N] [--list]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

HARD_LIMIT = 250
WARN_LIMIT = 200

# Directories whose contents are generated, vendored, or not source.
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".venv",
        "node_modules",
        ".next",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".import_linter_cache",
        "dist",
        "build",
        "htmlcov",
        "contracts",  # generated TypeScript
    }
)

SOURCE_SUFFIXES = frozenset({".py", ".ts", ".tsx"})

# Documented exceptions. Each needs a reason; see instructions.md section 5.1.
EXCEPTIONS: dict[str, str] = {
    "packages/core/src/factory_core/migrations/versions/0001_initial_schema.py": (
        "A migration is one atomic schema change. Splitting it would create revisions "
        "that cannot be applied independently."
    ),
}


def _relative(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def _iter_sources(root: Path):  # type: ignore[no-untyped-def]
    """Yield every source file that is subject to the limit."""
    for path in root.rglob("*"):
        if path.suffix not in SOURCE_SUFFIXES or not path.is_file():
            continue
        if EXCLUDED_DIRS & set(path.parts):
            continue
        yield path


def main() -> int:
    """Check every source file. Returns a process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=HARD_LIMIT)
    parser.add_argument("--warn", type=int, default=WARN_LIMIT)
    parser.add_argument("--list", action="store_true", help="List the 15 largest files")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    sizes: list[tuple[int, str]] = []
    violations: list[tuple[str, int]] = []
    warnings: list[tuple[str, int]] = []

    for path in _iter_sources(root):
        relative = _relative(path, root)
        lines = len(path.read_text(encoding="utf-8", errors="replace").splitlines())
        sizes.append((lines, relative))

        if relative in EXCEPTIONS:
            continue
        if lines > args.limit:
            violations.append((relative, lines))
        elif lines > args.warn:
            warnings.append((relative, lines))

    if args.list:
        print(f"Largest source files (limit {args.limit}):")  # noqa: T201
        for lines, relative in sorted(sizes, reverse=True)[:15]:
            print(f"  {lines:>4}  {relative}")  # noqa: T201
        print()  # noqa: T201

    for relative, lines in sorted(warnings, key=lambda item: -item[1]):
        print(f"note: {relative} is {lines} lines (soft limit {args.warn})")  # noqa: T201

    if violations:
        print(f"\nFAIL: {len(violations)} file(s) exceed the {args.limit}-line limit:")  # noqa: T201
        for relative, lines in sorted(violations, key=lambda item: -item[1]):
            print(f"  {lines:>4}  {relative}")  # noqa: T201
        print("\nSplit by responsibility, not arbitrarily. See instructions.md section 5.1.")  # noqa: T201
        return 1

    print(f"OK: {len(sizes)} source files, none over {args.limit} lines.")  # noqa: T201
    return 0


if __name__ == "__main__":
    sys.exit(main())
