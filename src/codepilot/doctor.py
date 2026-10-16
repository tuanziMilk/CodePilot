"""Check the local runtime without reading or printing a model API key."""

from __future__ import annotations

import importlib.util
import os
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    env_path = Path(os.environ.get("CODEPILOT_ENV_FILE", root / ".env"))
    values = dotenv_values(env_path) if env_path.is_file() else {}
    bash_path = Path(
        os.environ.get("GIT_BASH_PATH")
        or values.get("GIT_BASH_PATH")
        or r"C:\Program Files\Git\bin\bash.exe"
    )
    print(f"Python: {sys.version.split()[0]} ({sys.executable})")
    print(f"CodePilot source: {root / 'src' / 'codepilot'}")
    ok = sys.version_info >= (3, 11)
    for dependency in ("pydantic", "httpx", "dotenv", "pytest"):
        found = importlib.util.find_spec(dependency) is not None
        print(f"{dependency}: {'OK' if found else 'MISSING'}")
        ok = ok and found
    print(f"Git: {shutil.which('git') or 'MISSING'}")
    print(f"Git Bash: {bash_path} ({'OK' if bash_path.is_file() else 'MISSING'})")
    print(f"Local .env: {'present' if env_path.is_file() else 'not created; offline commands still work'}")
    print("No network request was made. API key values are never displayed.")
    return 0 if ok and shutil.which("git") and bash_path.is_file() else 1
