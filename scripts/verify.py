"""Run the same verification steps used by CI."""

from __future__ import annotations

import subprocess
import sys


COMMANDS = [
    [sys.executable, "-m", "compileall", "-q", "backend", "tests", "run.py"],
    [
        sys.executable,
        "-c",
        "from backend.app.main import app; print(app.title)",
    ],
    [sys.executable, "-m", "pytest", "-q"],
]


def main() -> int:
    for command in COMMANDS:
        print(f"> {' '.join(command)}")
        result = subprocess.run(command, check=False)

        if result.returncode != 0:
            return result.returncode

    print("All verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
