"""Run the complete quality gate with the active Python interpreter."""

import os
import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
    for args in (
        ("pytest",),
        ("ruff", "check", "."),
        ("ruff", "format", "--check", "."),
        ("pyright",),
    ):
        print(f"Running: {sys.executable} -m {' '.join(args)}", flush=True)
        result = subprocess.run([sys.executable, "-m", *args], cwd=root, env=env, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
