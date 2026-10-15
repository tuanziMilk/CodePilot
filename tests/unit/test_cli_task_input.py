from pathlib import Path

import pytest

from codepilot.cli.main import (
    build_parser,
    resolve_planning_mode,
    resolve_reproduction_policy,
    resolve_run_input,
)


def test_cli_resolves_task_file_into_run_input(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    task_path = tasks_dir / "task.json"
    task_path.write_text(
        """
        {
          "task_id": "tiny-task",
          "repository": "../repo",
          "issue_description": "Fix the defect.",
          "verification_command": "python -m pytest -q",
          "allowed_files": ["calculator.py"]
        }
        """,
        encoding="utf-8",
    )
    args = build_parser().parse_args(["--task-file", str(task_path)])

    task, workspace, verify, allowed, task_id, requires_reproduction = resolve_run_input(args)

    assert task == "Fix the defect."
    assert workspace == (tmp_path / "repo").resolve()
    assert verify == "python -m pytest -q"
    assert allowed == frozenset({"calculator.py"})
    assert task_id == "tiny-task"
    assert requires_reproduction is True


def test_cli_resolves_reproduction_policy_for_evaluation_arms() -> None:
    assert resolve_reproduction_policy("task", True) is True
    assert resolve_reproduction_policy("task", False) is False
    assert resolve_reproduction_policy("on", False) is True
    assert resolve_reproduction_policy("off", True) is False


def test_cli_preserves_legacy_planning_and_supports_strict_ablation() -> None:
    assert resolve_planning_mode(None, False) == "optional"
    assert resolve_planning_mode(None, True) == "required"
    assert resolve_planning_mode("off", False) == "off"
    assert resolve_planning_mode("required", False) == "required"
    with pytest.raises(ValueError, match="cannot be combined"):
        resolve_planning_mode("off", True)
