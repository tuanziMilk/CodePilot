"""A narrow Git Bash process adapter for Windows Phase 1."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    stdout: str
    stderr: str
    return_code: int | None
    duration_ms: int
    timed_out: bool = False


class GitBashEnvironment:
    """Execute an already-authorized command at the bounded workspace root."""

    def __init__(
        self,
        workspace_root: Path,
        bash_path: Path,
        *,
        output_limit: int = 12_000,
    ) -> None:
        self.workspace_root = workspace_root.resolve()
        self.bash_path = bash_path
        self.output_limit = output_limit
        if not bash_path.is_file():
            raise ValueError(f"Git Bash executable was not found: {bash_path}")

    def run(self, command: str, timeout_seconds: float) -> ProcessResult:
        """Run with explicit argv and cwd, never with Python shell=True."""

        started = time.perf_counter()
        try:
            completed = subprocess.run(
                [str(self.bash_path), "-lc", command],
                cwd=self.workspace_root,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1", "PYTHONDONTWRITEBYTECODE": "1"},
                timeout=timeout_seconds,
                shell=False,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            duration_ms = round((time.perf_counter() - started) * 1000)
            return ProcessResult(
                stdout=self._bound(error.stdout or ""),
                stderr=self._bound(error.stderr or ""),
                return_code=None,
                duration_ms=duration_ms,
                timed_out=True,
            )

        duration_ms = round((time.perf_counter() - started) * 1000)
        return ProcessResult(
            # ``capture_output=True`` normally yields strings, but Windows process
            # adapters can still expose a missing stream. A missing stream means
            # "no output", not a reason to turn a completed command into a tool
            # error.
            stdout=self._bound(completed.stdout),
            stderr=self._bound(completed.stderr),
            return_code=completed.returncode,
            duration_ms=duration_ms,
        )

    def git_commit(self) -> str | None:
        """Return HEAD for reproducibility; absence of Git history is valid."""

        result = self.run("git rev-parse HEAD", timeout_seconds=5)
        return result.stdout.strip() if result.return_code == 0 else None

    def git_diff(self) -> str | None:
        """Capture the bounded working-tree diff for the final report."""

        result = self.run("git diff --", timeout_seconds=10)
        return result.stdout if result.return_code == 0 else None

    def _bound(self, value: str | bytes | None) -> str:
        text = value.decode(errors="replace") if isinstance(value, bytes) else (value or "")
        if len(text) <= self.output_limit:
            return text
        return text[: self.output_limit] + "\n... [output truncated by CodePilot]"
