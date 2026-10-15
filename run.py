"""Run this checkout without changing an existing editable CodePilot install."""

from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "src"
sys.path.insert(0, str(SOURCE))
os.environ["PYTHONPATH"] = str(SOURCE) + os.pathsep + os.environ.get("PYTHONPATH", "")
os.environ.setdefault("CODEPILOT_ENV_FILE", str(ROOT / ".env"))

COMMANDS = {
    "run": "codepilot.cli.main",
    "eval": "codepilot.evaluation.runner",
    "prepare": "codepilot.benchmarks.prepare",
    "validate": "codepilot.benchmarks.validate",
    "report": "codepilot.evaluation.report",
    "view": "codepilot.trajectory.viewer",
    "demo": "codepilot.demo",
    "doctor": "codepilot.doctor",
    "test": "pytest",
}


def main() -> int:
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print("Usage: python run.py {" + ",".join(COMMANDS) + "} [options]")
        print("Use 'python run.py doctor' for a local installation check.")
        return 0 if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"} else 2
    command = sys.argv.pop(1)
    module = importlib.import_module(COMMANDS[command])
    return module.main()


if __name__ == "__main__":
    raise SystemExit(main())
