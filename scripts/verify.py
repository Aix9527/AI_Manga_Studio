"""Run the same verification steps used by CI."""

from __future__ import annotations

import subprocess
import sys


COMMANDS = [
    [
        sys.executable,
        "-m",
        "compileall",
        "-q",
        "backend",
        "tests",
        "scripts",
        "run.py",
    ],
    [
        sys.executable,
        "-m",
        "ruff",
        "check",
        "backend",
        "tests",
        "scripts",
        "run.py",
    ],
    [
        sys.executable,
        "-c",
        (
            "from backend.app.main import app; "
            "assert app.title == 'AI Manga Studio'; "
            "print(app.title)"
        ),
    ],
    [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "--maxfail=1",
    ],
]


def main() -> int:
    for command in COMMANDS:
        print(f"> {' '.join(command)}")

        result = subprocess.run(command, check=False)

        if result.returncode != 0:
            print(
                f"Verification failed with exit code "
                f"{result.returncode}: {' '.join(command)}"
            )
            return result.returncode

    result = subprocess.run(
        ["git", "status", "--porcelain"],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return result.returncode

    if result.stdout.strip():
        print("Verification left repository changes:")
        print(result.stdout)
        return 1

    print("All verification checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
