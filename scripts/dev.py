"""Start the whole stack with one command: ``uv run dev``.

Runs the API, the worker and the web app together, prefixing each line with its source so
one terminal stays readable. Ctrl+C stops all three.

Convenience only. Running the three commands in separate terminals is equally valid and
gives clearer output when debugging one of them:

    uv run dev-api
    uv run dev-worker
    pnpm --filter web dev
"""

from __future__ import annotations

import shutil
import signal
import subprocess
import sys
import threading
from pathlib import Path
from types import FrameType

ROOT = Path(__file__).resolve().parent.parent

# Colours make the interleaved output scannable. Windows Terminal, macOS and Linux
# terminals all handle these; a plain pipe just shows the escape codes, which is harmless.
PREFIXES: dict[str, str] = {
    "api": "\033[36m",
    "worker": "\033[35m",
    "web": "\033[32m",
}
RESET = "\033[0m"


def _pnpm() -> str | None:
    """Locate pnpm, which is a .cmd shim on Windows and needs resolving."""
    return shutil.which("pnpm")


def _stream(name: str, process: subprocess.Popen[str]) -> None:
    """Forward one process's output, prefixed with its name."""
    colour = PREFIXES.get(name, "")
    assert process.stdout is not None  # noqa: S101 - guaranteed by the Popen call below
    for line in process.stdout:
        sys.stdout.write(f"{colour}[{name}]{RESET} {line}")
        sys.stdout.flush()


def main() -> int:
    """Start every process and block until one exits or the user interrupts."""
    pnpm = _pnpm()
    if pnpm is None:
        print("pnpm not found on PATH. Install it, or run the three commands separately.")  # noqa: T201
        return 1

    commands: dict[str, list[str]] = {
        "api": [sys.executable, "-m", "factory_api"],
        "worker": [sys.executable, "-m", "factory_worker"],
        "web": [pnpm, "--filter", "web", "dev"],
    }

    processes: dict[str, subprocess.Popen[str]] = {}
    threads: list[threading.Thread] = []

    def shutdown(_signum: int, _frame: FrameType | None) -> None:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()

    signal.signal(signal.SIGINT, shutdown)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, shutdown)

    try:
        for name, command in commands.items():
            process = subprocess.Popen(  # noqa: S603 - fixed commands, no user input
                command,
                cwd=ROOT,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )
            processes[name] = process
            thread = threading.Thread(target=_stream, args=(name, process), daemon=True)
            thread.start()
            threads.append(thread)

        print(f"\n{PREFIXES['web']}Web{RESET}  http://127.0.0.1:3000")  # noqa: T201
        print(f"{PREFIXES['api']}API{RESET}  http://127.0.0.1:8000/docs\n")  # noqa: T201

        # Exit as soon as any process dies. A stack running with one process missing looks
        # healthy and behaves mysteriously; failing loudly is better.
        while True:
            for name, process in processes.items():
                code = process.poll()
                if code is not None:
                    print(f"\n[{name}] exited with code {code}; stopping the rest.")  # noqa: T201
                    shutdown(0, None)
                    return code
            for thread in threads:
                thread.join(timeout=0.2)
    except KeyboardInterrupt:
        shutdown(0, None)
        return 0
    finally:
        for process in processes.values():
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
