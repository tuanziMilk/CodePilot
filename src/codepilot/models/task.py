"""Evaluation-friendly Coding Task contract.

TaskSpec is deliberately small: it captures only the facts needed to reproduce
one bounded coding task. It is not a workflow engine or a benchmark framework.
"""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TaskSpecError(ValueError):
    """Raised when a task JSON document cannot safely define a run."""


class TaskSpec(BaseModel):
    """The stable, serializable input for one Coding Agent task."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(min_length=1)
    repository: str = Field(min_length=1)
    issue_description: str = Field(min_length=1)
    verification_command: str = Field(min_length=1)
    allowed_files: tuple[str, ...] = Field(min_length=1)
    visible_tests: tuple[str, ...] = ()
    forbidden_files: tuple[str, ...] = ()
    success_condition: str | None = None
    initial_commit: str | None = None
    requires_reproduction: bool = True
    acceptance_test_file: str | None = None
    difficulty: str = "easy"
    task_family: str = "synthetic"

    @model_validator(mode="after")
    def validate_file_rules(self) -> TaskSpec:
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", self.task_id):
            raise ValueError("task_id must be a safe directory name using letters, digits, _ or -.")
        if Path(self.repository).is_absolute():
            raise ValueError("repository must be relative to the task file.")
        for path in (*self.allowed_files, *self.forbidden_files, *self.visible_tests):
            posix = PurePosixPath(path.replace("\\", "/"))
            windows = PureWindowsPath(path)
            if not path or posix.is_absolute() or windows.drive or ".." in posix.parts:
                raise ValueError("File rules must contain safe workspace-relative paths.")
        if self.initial_commit and not re.fullmatch(r"[0-9a-fA-F]{40}", self.initial_commit):
            raise ValueError("initial_commit must be a full 40-character Git SHA.")
        overlap = set(self.allowed_files) & set(self.forbidden_files)
        if overlap:
            raise ValueError(f"allowed_files and forbidden_files overlap: {sorted(overlap)}")
        return self


def load_task_spec(path: Path) -> TaskSpec:
    """Load a JSON task specification without coupling it to the CLI."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise TaskSpecError(f"Unable to read task file {path}: {error}") from error
    except json.JSONDecodeError as error:
        raise TaskSpecError(f"Task file {path} contains invalid JSON: {error}") from error

    try:
        return TaskSpec.model_validate(payload)
    except ValueError as error:
        raise TaskSpecError(f"Task file {path} is invalid: {error}") from error


def resolve_task_repository(task_path: Path, task: TaskSpec) -> Path:
    """Resolve a task repository relative to its task JSON document."""

    return (task_path.parent / task.repository).resolve()
