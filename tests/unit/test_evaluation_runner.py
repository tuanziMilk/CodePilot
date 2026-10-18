import subprocess
from pathlib import Path

from codepilot.evaluation.runner import (
    DEFAULT_CONFIGS,
    _clone_baseline,
    aggregate_records,
    evaluation_schedule,
    materialize_task_file,
    retrieval_file_recall,
    retrieval_hit_rank,
)
from codepilot.models.task import TaskSpec, load_task_spec


def test_evaluation_configs_expose_only_the_intended_harness_switches() -> None:
    assert DEFAULT_CONFIGS["basic"].cli_arguments() == [
        "--planning-mode",
        "off",
        "--reproduction-policy",
        "off",
        "--retrieval-mode",
        "none",
        "--context-mode",
        "compact",
    ]
    assert DEFAULT_CONFIGS["full"].cli_arguments() == [
        "--planning-mode",
        "required",
        "--reproduction-policy",
        "on",
        "--retrieval-mode",
        "lexical",
        "--context-mode",
        "compact",
    ]


def test_materialized_task_points_to_case_workspace(tmp_path: Path) -> None:
    task = TaskSpec(
        task_id="task",
        repository="../source",
        issue_description="Fix it.",
        verification_command="python -m pytest -q",
        allowed_files=("calculator.py",),
        initial_commit="a" * 40,
    )

    materialized = materialize_task_file(task, tmp_path / "task.json")

    assert load_task_spec(materialized).repository == "workspace"
    assert task.repository == "../source"


def test_aggregate_records_groups_success_and_observable_metrics() -> None:
    summary = aggregate_records(
        [
            {
                "config": "basic",
                "terminal_state": "verified_success",
                "evaluation_outcome": "success",
                "acceptance_passed": True,
                "steps": 4,
                "token_usage": {"input_tokens": 80, "output_tokens": 20, "total_tokens": 100},
                "metrics": {
                    "run_elapsed_ms": 1000,
                    "llm_latency_ms": 300,
                    "tool_error_count": 1,
                    "context_compaction_count": 2,
                    "context_request_count": 4,
                    "total_context_chars_sent": 40_000,
                    "context_chars_saved": 10_000,
                    "max_context_chars_before": 20_000,
                    "max_context_chars_after": 10_000,
                    "max_context_messages_sent": 8,
                    "max_context_steps_compacted": 3,
                },
                "configuration": {"retrieval_mode": "lexical"},
                "changed_files": ["calculator.py"],
                "retrieval_hit_rank": 2,
                "reference_fix_files": ["calculator.py", "service.py"],
                "retrieval_paths": ["tests.py", "calculator.py"],
                "verified_at_step_limit": True,
            },
            {
                "config": "basic",
                "terminal_state": "max_steps",
                "evaluation_outcome": "failed",
                "acceptance_passed": False,
                "steps": 6,
                "token_usage": {"input_tokens": 150, "output_tokens": 50, "total_tokens": 200},
                "metrics": {
                    "run_elapsed_ms": 3000,
                    "llm_latency_ms": 500,
                    "tool_denied_count": 2,
                    "context_compaction_count": 4,
                    "context_request_count": 6,
                    "total_context_chars_sent": 72_000,
                    "context_chars_saved": 18_000,
                    "max_context_chars_before": 30_000,
                    "max_context_chars_after": 12_000,
                    "max_context_messages_sent": 10,
                    "max_context_steps_compacted": 5,
                },
                "configuration": {"retrieval_mode": "lexical"},
                "changed_files": ["calculator.py"],
                "retrieval_hit_rank": None,
                "reference_fix_files": ["calculator.py", "service.py"],
                "retrieval_paths": ["tests.py"],
            },
        ]
    )

    basic = summary["by_config"]["basic"]
    assert basic["runs"] == 2
    assert basic["verified_successes"] == 1
    assert basic["success_rate"] == 0.5
    assert basic["avg_steps"] == 5
    assert basic["avg_total_tokens"] == 150
    assert basic["avg_input_tokens"] == 115
    assert basic["avg_output_tokens"] == 35
    assert basic["avg_run_elapsed_ms"] == 2000
    assert basic["avg_llm_latency_ms"] == 400
    assert basic["tool_errors"] == 1
    assert basic["tool_denied"] == 2
    assert basic["step_limit_successes"] == 1
    assert basic["context_compactions"] == 6
    assert basic["avg_context_request_count"] == 5
    assert basic["avg_total_context_chars_sent"] == 56_000
    assert basic["avg_context_chars_saved"] == 14_000
    assert basic["avg_max_context_chars_before"] == 25_000
    assert basic["avg_max_context_chars_after"] == 11_000
    assert basic["avg_max_context_messages_sent"] == 9
    assert basic["avg_max_context_steps_compacted"] == 4
    assert basic["retrieval_hit_at_1_rate"] == 0
    assert basic["retrieval_hit_at_3_rate"] == 0.5
    assert basic["retrieval_reference_hit_at_1_rate"] == 0
    assert basic["avg_retrieval_reference_file_recall"] == 0.25


def test_evaluation_schedule_rotates_config_order_deterministically() -> None:
    first = object()
    second = object()

    schedule = evaluation_schedule([first, second], ["full-uncompacted", "full"], 2)

    assert schedule == [
        (first, "full-uncompacted", 1),
        (first, "full", 1),
        (first, "full", 2),
        (first, "full-uncompacted", 2),
        (second, "full", 1),
        (second, "full-uncompacted", 1),
        (second, "full-uncompacted", 2),
        (second, "full", 2),
    ]


def test_retrieval_hit_rank_uses_first_changed_file_match() -> None:
    assert retrieval_hit_rank(
        ["service.py", "model.py"],
        ["tests.py", "model.py", "service.py"],
    ) == 2
    assert retrieval_hit_rank(["service.py"], ["tests.py"]) is None


def test_retrieval_file_recall_measures_multi_file_reference_coverage() -> None:
    assert retrieval_file_recall(
        ["package/service.py", "package/store.py"],
        ["README.md", "package\\store.py"],
    ) == 0.5
    assert retrieval_file_recall([], ["package/store.py"]) is None


def test_clone_baseline_uses_committed_initial_state_not_source_worktree(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _run_git(["init", "--quiet"], source)
    _run_git(["config", "user.email", "test@example.com"], source)
    _run_git(["config", "user.name", "CodePilot Test"], source)
    source_file = source / "calculator.py"
    source_file.write_text("return a - b\n", encoding="utf-8")
    _run_git(["add", "calculator.py"], source)
    _run_git(["commit", "--quiet", "-m", "buggy baseline"], source)
    initial_commit = _run_git(["rev-parse", "HEAD"], source).stdout.strip()
    source_file.write_text("return a + b\n", encoding="utf-8")

    workspace = tmp_path / "case" / "workspace"
    _clone_baseline(source, workspace, initial_commit)

    assert (workspace / "calculator.py").read_text(encoding="utf-8") == "return a - b\n"
    assert _run_git(["rev-parse", "HEAD"], workspace).stdout.strip() == initial_commit


def _run_git(arguments: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    return result
