"""Real Git/checker subprocesses with an offline stand-in for the model CLI."""

import json
import subprocess
from pathlib import Path

import pytest

from codepilot.evaluation import runner
from codepilot.models.task import TaskSpec


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8", check=True
    )
    return result.stdout.strip()


@pytest.fixture
def evaluation_task(tmp_path: Path) -> tuple[TaskSpec, Path, Path, Path]:
    repo = tmp_path / "source"
    repo.mkdir()
    (repo / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (repo / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    _git(repo, "init", "--quiet")
    _git(repo, "-c", "user.email=test@example.com", "-c", "user.name=Test", "add", ".")
    _git(
        repo,
        "-c",
        "user.email=test@example.com",
        "-c",
        "user.name=Test",
        "commit",
        "--quiet",
        "-m",
        "bug baseline",
    )
    acceptance = tmp_path / "test_acceptance.py"
    acceptance.write_text(
        "from calculator import add\n\ndef test_unseen_inputs():\n    assert add(10, 5) == 15\n",
        encoding="utf-8",
    )
    task = TaskSpec(
        task_id="addition",
        repository="source",
        issue_description="Fix addition.",
        verification_command="python -m pytest test_calculator.py -q",
        allowed_files=("calculator.py",),
        visible_tests=("test_calculator.py",),
        initial_commit=_git(repo, "rev-parse", "HEAD"),
        acceptance_test_file="test_acceptance.py",
    )
    path = tmp_path / "task.json"
    path.write_text(task.model_dump_json(), encoding="utf-8")
    return task, path, repo, acceptance


def _mock_cli(
    monkeypatch: pytest.MonkeyPatch,
    *,
    fix: str = "a + b",
    terminal: str = "verified_success",
    extra_file: bool = False,
    tamper_acceptance: Path | None = None,
) -> None:
    original = runner._process

    def process(command: list[str], *, cwd: Path, timeout: float, env=None):
        if "codepilot.cli.main" not in command:
            return original(command, cwd=cwd, timeout=timeout, env=env)
        task_path = Path(command[command.index("--task-file") + 1])
        # The independent test path must not leak into the task passed to the Agent.
        assert "acceptance_test_file" not in json.loads(task_path.read_text(encoding="utf-8"))
        workspace = task_path.parent / "workspace"
        (workspace / "calculator.py").write_text(
            f"def add(a, b):\n    return {fix}\n", encoding="utf-8"
        )
        if extra_file:
            (workspace / "unapproved.py").write_text("tampered = True\n", encoding="utf-8")
        if tamper_acceptance:
            tamper_acceptance.write_text("def test_fake():\n    assert True\n", encoding="utf-8")
        artifacts = Path(command[command.index("--artifacts-dir") + 1]) / "offline-test"
        artifacts.mkdir(parents=True)
        (artifacts / "final_summary.json").write_text(
            json.dumps(
                {
                    "terminal_state": terminal,
                    "verification_passed": terminal == "verified_success",
                    "steps": 3,
                    "retry_count": 0,
                    "token_usage": {"total_tokens": 50},
                    "metrics": {"run_elapsed_ms": 100, "tool_error_count": 0},
                }
            ),
            encoding="utf-8",
        )
        (artifacts / "run_metadata.json").write_text(
            json.dumps({"model": "offline-test", "llm_api_key": "DO_NOT_EXPORT"}), encoding="utf-8"
        )
        return {
            "stdout": "offline fixture",
            "stderr": "",
            "return_code": 0 if terminal == "verified_success" else 1,
            "timed_out": False,
            "duration_ms": 1,
            "command": command,
        }

    monkeypatch.setattr(runner, "_process", process)


def _case(tmp_path: Path, data, config: str = "basic"):
    task, path, repo, acceptance = data
    return runner.run_case(
        project_root=tmp_path,
        task_path=path,
        task=task,
        source_repo=repo,
        acceptance_path=acceptance,
        config=runner.DEFAULT_CONFIGS[config],
        case_dir=tmp_path / "case",
    )


def test_evaluator_uses_fresh_commit_and_external_acceptance(
    tmp_path, evaluation_task, monkeypatch
):
    task, _, repo, _ = evaluation_task
    # A previous manual repair in the source checkout must not contaminate baseline.
    (repo / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    _mock_cli(monkeypatch)
    result = _case(tmp_path, evaluation_task)
    assert result["evaluation_outcome"] == "success", result
    assert result["initial_commit"] == task.initial_commit
    assert result["baseline_test_return_code"] == 1
    assert result["baseline_acceptance_return_code"] == 1
    assert result["acceptance_passed"] is True
    assert result["changed_files"] == ["calculator.py"]
    assert "llm_api_key" not in result["run_metadata"]
    assert (tmp_path / "case" / "changes.diff").is_file()
    assert not (tmp_path / "case" / "workspace" / "test_acceptance.py").exists()


def test_visible_test_overfit_cannot_pass_external_acceptance(
    tmp_path, evaluation_task, monkeypatch
):
    _mock_cli(monkeypatch, fix="5")
    result = _case(tmp_path, evaluation_task)
    assert result["terminal_state"] == "verified_success"
    assert result["acceptance_passed"] is False
    assert result["evaluation_outcome"] == "failed"


def test_correct_patch_with_max_steps_is_still_failed(tmp_path, evaluation_task, monkeypatch):
    _mock_cli(monkeypatch, terminal="max_steps")
    result = _case(tmp_path, evaluation_task)
    assert result["acceptance_passed"] is True
    assert result["terminal_state"] == "max_steps"
    assert result["evaluation_outcome"] == "failed"


def test_untracked_source_mutation_fails_audit(tmp_path, evaluation_task, monkeypatch):
    _mock_cli(monkeypatch, extra_file=True)
    result = _case(tmp_path, evaluation_task)
    assert result["acceptance_passed"] is True
    assert result["disallowed_files"] == ["unapproved.py"]
    assert result["evaluation_outcome"] == "failed"


def test_acceptance_tampering_invalidates_apparent_test_pass(
    tmp_path, evaluation_task, monkeypatch
):
    _mock_cli(monkeypatch, tamper_acceptance=evaluation_task[3])
    result = _case(tmp_path, evaluation_task)
    assert result["acceptance_passed"] is True
    assert result["acceptance_unchanged"] is False
    assert result["evaluation_outcome"] == "failed"


def test_one_case_infrastructure_error_does_not_abort_later_cases(
    tmp_path, evaluation_task, monkeypatch
):
    _mock_cli(monkeypatch)
    monkeypatch.setattr(runner.Settings, "from_env", lambda: None)
    original = runner._visible_test
    calls = 0

    def fail_once(task, workspace, timeout):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("fixture process unavailable")
        return original(task, workspace, timeout)

    monkeypatch.setattr(runner, "_visible_test", fail_once)
    output = tmp_path / "output"
    assert (
        runner.main(
            [
                "--task-file",
                str(evaluation_task[1]),
                "--config",
                "basic",
                "--config",
                "full",
                "--output-dir",
                str(output),
            ]
        )
        == 0
    )
    summary = json.loads((output / "evaluation_summary.json").read_text(encoding="utf-8"))
    assert [record["evaluation_outcome"] for record in summary["records"]] == [
        "infra_error",
        "success",
    ]
    assert (output / "report.csv").exists()


def test_suite_dry_run_has_no_api_or_output_writes(tmp_path, evaluation_task, monkeypatch, capsys):
    suite = tmp_path / "suite.json"
    suite.write_text(json.dumps({"tasks": ["task.json"]}), encoding="utf-8")
    monkeypatch.setattr(runner, "run_case", lambda **kwargs: pytest.fail("dry run executed a case"))
    output = tmp_path / "never_created"
    assert runner.main(["--suite", str(suite), "--dry-run", "--output-dir", str(output)]) == 0
    assert json.loads(capsys.readouterr().out)["cases"] == 4
    assert not output.exists()


def test_duplicate_tasks_rejected_before_writes(tmp_path, evaluation_task):
    _, path, _, _ = evaluation_task
    output = tmp_path / "never_created"
    assert (
        runner.main(
            ["--task-file", str(path), "--task-file", str(path), "--output-dir", str(output)]
        )
        == 2
    )
    assert not output.exists()


def test_no_measurement_is_not_reported_as_zero():
    data = runner.aggregate_records([{"config": "basic", "evaluation_outcome": "infra_error"}])
    assert data["by_config"]["basic"]["avg_total_tokens"] is None
    assert data["by_config"]["basic"]["tool_errors"] is None
    assert data["by_config"]["basic"]["total_tokens_samples"] == 0


def test_existing_workspace_is_preserved(tmp_path, evaluation_task):
    task, _, repo, _ = evaluation_task
    workspace = tmp_path / "existing"
    workspace.mkdir()
    marker = workspace / "precious.txt"
    marker.write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="Refusing to reuse"):
        runner._clone_baseline(repo, workspace, task.initial_commit)
    assert marker.read_text(encoding="utf-8") == "keep"
