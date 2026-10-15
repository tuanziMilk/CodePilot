import json
from pathlib import Path

import pytest

from codepilot.models.task import TaskSpecError, load_task_spec, resolve_task_repository


def test_task_spec_loads_and_resolves_repository_relative_to_task_file(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    repo_dir = tmp_path / "repos" / "email_bug"
    tasks_dir.mkdir()
    repo_dir.mkdir(parents=True)
    task_path = tasks_dir / "email.json"
    task_path.write_text(
        json.dumps(
            {
                "task_id": "email-normalization",
                "repository": "../repos/email_bug",
                "issue_description": "Normalize email addresses.",
                "verification_command": "python -m pytest -q",
                "allowed_files": ["email_utils.py"],
                "visible_tests": ["test_email_utils.py"],
                "forbidden_files": ["test_email_utils.py"],
            }
        ),
        encoding="utf-8",
    )

    task = load_task_spec(task_path)

    assert task.requires_reproduction is True
    assert resolve_task_repository(task_path, task) == repo_dir.resolve()


def test_task_spec_rejects_conflicting_file_rules(tmp_path: Path) -> None:
    task_path = tmp_path / "bad.json"
    task_path.write_text(
        json.dumps(
            {
                "task_id": "bad-task",
                "repository": "repo",
                "issue_description": "Fix it.",
                "verification_command": "python -m pytest -q",
                "allowed_files": ["calculator.py"],
                "forbidden_files": ["calculator.py"],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(TaskSpecError, match="overlap"):
        load_task_spec(task_path)
