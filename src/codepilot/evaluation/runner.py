"""Reproducible evaluation: fresh Git baseline, bounded run, external acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PureWindowsPath
from typing import Any

from dotenv import load_dotenv

from codepilot.config.settings import Settings
from codepilot.models.task import TaskSpec, load_task_spec, resolve_task_repository
from codepilot.permissions.policy import PermissionPolicy


@dataclass(frozen=True)
class EvaluationConfig:
    """One controlled Harness configuration used by an evaluation case."""

    name: str
    require_plan: bool
    reproduction_policy: str
    retrieval_mode: str
    context_mode: str = "compact"

    def cli_arguments(self) -> list[str]:
        return [
            "--planning-mode",
            "required" if self.require_plan else "off",
            "--reproduction-policy",
            self.reproduction_policy,
            "--retrieval-mode",
            self.retrieval_mode,
            "--context-mode",
            self.context_mode,
        ]


DEFAULT_CONFIGS = {
    "basic": EvaluationConfig("basic", False, "off", "none"),
    "reliable": EvaluationConfig("reliable", True, "on", "none"),
    "retrieval": EvaluationConfig("retrieval", False, "off", "lexical"),
    "full": EvaluationConfig("full", True, "on", "lexical"),
}

# Opt-in arms for isolating context compaction without increasing the default
# four-arm evaluation cost.
OPTIONAL_CONFIGS = {
    "basic-uncompacted": EvaluationConfig("basic-uncompacted", False, "off", "none", "full"),
    "full-uncompacted": EvaluationConfig("full-uncompacted", True, "on", "lexical", "full"),
}
ALL_CONFIGS = {**DEFAULT_CONFIGS, **OPTIONAL_CONFIGS}


@dataclass(frozen=True)
class PreparedTask:
    path: Path
    task: TaskSpec
    source_repo: Path
    acceptance_path: Path
    reference_fix_files: tuple[str, ...] = ()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Evaluate CodePilot from clean Git baselines.")
    parser.add_argument("--task-file", type=Path, action="append", default=[])
    parser.add_argument(
        "--suite", type=Path, help="JSON manifest; task paths are relative to this file."
    )
    parser.add_argument("--config", choices=tuple(ALL_CONFIGS), action="append")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--list", action="store_true", help="Validate and list cases; no API or writes."
    )
    parser.add_argument("--dry-run", action="store_true", help="Same as --list; no API or writes.")
    parser.add_argument(
        "--case-timeout", type=float, default=600, help="Seconds allowed for each Agent CLI."
    )
    parser.add_argument(
        "--test-timeout", type=float, default=120, help="Seconds per baseline/acceptance check."
    )
    return parser


def prepare_tasks(paths: list[Path], suite: Path | None = None) -> list[PreparedTask]:
    """Validate the complete plan before making any output directory."""

    selected = list(paths)
    if suite:
        manifest = json.loads(suite.read_text(encoding="utf-8"))
        entries = manifest.get("tasks") if isinstance(manifest, dict) else manifest
        if not isinstance(entries, list) or not all(isinstance(p, str) for p in entries):
            raise ValueError("Suite must contain a tasks array of relative TaskSpec paths.")
        for entry in entries:
            relative = Path(entry)
            if relative.is_absolute() or ".." in relative.parts or re.match(r"^[A-Za-z]:", entry):
                raise ValueError("Suite entries must be safe paths beneath the suite directory.")
            resolved = (suite.resolve().parent / relative).resolve()
            if not resolved.is_relative_to(suite.resolve().parent):
                raise ValueError("Suite task path escapes the suite directory.")
            selected.append(resolved)
    if not selected:
        raise ValueError("Provide --suite or at least one --task-file.")
    prepared: list[PreparedTask] = []
    identities: set[str] = set()
    source_paths: set[Path] = set()
    for path in selected:
        path = path.resolve()
        task = load_task_spec(path)
        if task.task_id.casefold() in identities or path in source_paths:
            raise ValueError(f"Duplicate task: {task.task_id}")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", task.task_id):
            raise ValueError("Unsafe task_id directory name.")
        identities.add(task.task_id.casefold())
        source_paths.add(path)
        if not task.initial_commit or not re.fullmatch(r"[0-9a-fA-F]{40}", task.initial_commit):
            raise ValueError(
                "Evaluation requires TaskSpec.initial_commit as a full 40-character SHA."
            )
        source = resolve_task_repository(path, task)
        if not source.is_dir() or not (source / ".git").exists():
            raise ValueError(f"Task repository is not a Git checkout: {source}")
        if not task.acceptance_test_file:
            raise ValueError(
                f"Task {task.task_id} needs acceptance_test_file outside its repository."
            )
        if (
            Path(task.acceptance_test_file).is_absolute()
            or PureWindowsPath(task.acceptance_test_file).drive
        ):
            raise ValueError("acceptance_test_file must be relative to its source TaskSpec.")
        acceptance = (path.parent / task.acceptance_test_file).resolve()
        if (
            not acceptance.is_file()
            or acceptance.suffix != ".py"
            or acceptance.is_relative_to(source)
        ):
            raise ValueError("acceptance_test_file must be an existing external Python test file.")
        PermissionPolicy("mvp-v1").authorize_command(task.verification_command)
        prepared.append(
            PreparedTask(
                path,
                task,
                source,
                acceptance,
                _reference_fix_files(path, task.task_id),
            )
        )
    return prepared


def _reference_fix_files(task_path: Path, task_id: str) -> tuple[str, ...]:
    """Read evaluator-only reference paths when using the generated benchmark layout."""

    reference_path = task_path.parent.parent / "reference" / f"{task_id}.json"
    if not reference_path.is_file():
        return ()
    payload = json.loads(reference_path.read_text(encoding="utf-8"))
    edits = payload.get("edits")
    paths = (
        [edit.get("path") for edit in edits if isinstance(edit, dict)]
        if isinstance(edits, list)
        else [payload.get("path")]
    )
    if not paths or not all(isinstance(path, str) and path for path in paths):
        raise ValueError(f"Invalid reference fix paths for task {task_id}.")
    normalized = tuple(dict.fromkeys(path.replace("\\", "/") for path in paths))
    if any(Path(path).is_absolute() or ".." in Path(path).parts for path in normalized):
        raise ValueError(f"Unsafe reference fix path for task {task_id}.")
    return normalized


def materialize_task_file(task: TaskSpec, destination: Path) -> Path:
    """Pass Agent-visible fields only; never reveal external acceptance location."""

    payload = task.model_dump(mode="json")
    payload["repository"] = "workspace"
    payload.pop("acceptance_test_file", None)
    destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return destination


def _process(
    command: list[str], *, cwd: Path, timeout: float, env: dict[str, str] | None = None
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        return {
            "command": command,
            "return_code": result.returncode,
            "stdout": result.stdout or "",
            "stderr": result.stderr or "",
            "timed_out": False,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }
    except subprocess.TimeoutExpired as error:

        def decode(value: str | bytes | None) -> str:
            return (
                value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
            )

        return {
            "command": command,
            "return_code": None,
            "stdout": decode(error.stdout),
            "stderr": decode(error.stderr),
            "timed_out": True,
            "duration_ms": round((time.perf_counter() - started) * 1000),
        }


def _git(arguments: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
        timeout=30,
    )


def _checked_git(arguments: list[str], *, cwd: Path | None = None) -> str:
    result = _git(arguments, cwd=cwd)
    if result.returncode:
        raise RuntimeError(f"Git {arguments[0]} failed: {result.stderr.strip()}")
    return result.stdout


def _clone_baseline(source_repo: Path, workspace: Path, initial_commit: str) -> None:
    if workspace.exists():
        raise ValueError(f"Refusing to reuse an existing workspace: {workspace}")
    _checked_git(["clone", "--quiet", "--no-hardlinks", str(source_repo), str(workspace)])
    _checked_git(["checkout", "--quiet", "--detach", initial_commit], cwd=workspace)
    if _checked_git(["rev-parse", "HEAD"], cwd=workspace).strip().lower() != initial_commit.lower():
        raise RuntimeError("Cloned HEAD does not match initial_commit.")


def _test_env(workspace: Path) -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join([str(workspace), str(workspace / "src")])
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    return env


def _visible_test(task: TaskSpec, workspace: Path, timeout: float) -> dict[str, Any]:
    tokens = shlex.split(task.verification_command)
    if tokens[0] in {"python", "python3"} and tokens[1:3] == ["-m", "pytest"]:
        command = [sys.executable, *tokens[1:]]
    elif tokens[0] == "pytest":
        command = [sys.executable, "-m", "pytest", *tokens[1:]]
    else:
        command = [
            os.getenv("GIT_BASH_PATH", r"C:\Program Files\Git\bin\bash.exe"),
            "-lc",
            task.verification_command,
        ]
    return _process(command, cwd=workspace, timeout=timeout, env=_test_env(workspace))


def _acceptance(path: Path, workspace: Path, timeout: float) -> dict[str, Any]:
    return _process(
        [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--import-mode=importlib",
            "--confcutdir",
            str(path.parent),
            str(path),
        ],
        cwd=workspace,
        timeout=timeout,
        env=_test_env(workspace),
    )


def _failed_test(result: dict[str, Any]) -> bool:
    """Pytest 1 is a test failure; collection/usage/timeout are invalid baselines."""
    output = result.get("stdout", "") + result.get("stderr", "")
    if result["return_code"] != 1 or result["timed_out"]:
        return False
    if "BUILD FAILURE" in output:
        return "There are test failures" in output or bool(re.search(r"Failures: [1-9]", output))
    return not any(marker in output for marker in ("ERROR collecting", "No tests were executed"))


def audit_workspace(workspace: Path, task: TaskSpec) -> dict[str, Any]:
    """Audit HEAD-relative tracked changes and all untracked files, including ignored files."""
    baseline = task.initial_commit or "HEAD"
    tracked = _checked_git(["diff", baseline, "--name-only", "-z"], cwd=workspace).split("\0")
    untracked = _checked_git(["ls-files", "--others", "-z"], cwd=workspace).split("\0")
    caches = {"__pycache__", ".pytest_cache", ".ruff_cache", "target"}
    changes = [p for p in tracked if p] + [
        p for p in untracked if p and not caches.intersection(Path(p).parts)
    ]
    changed = sorted({p.replace("\\", "/") for p in changes})
    allowed = {p.replace("\\", "/").casefold() for p in task.allowed_files}
    forbidden = {
        p.replace("\\", "/").casefold() for p in (*task.forbidden_files, *task.visible_tests)
    }
    disallowed = [p for p in changed if p.casefold() not in allowed or p.casefold() in forbidden]
    diff_check = _git(["diff", baseline, "--check"], cwd=workspace)
    head = _checked_git(["rev-parse", "HEAD"], cwd=workspace).strip()
    head_unchanged = not task.initial_commit or head.lower() == task.initial_commit.lower()
    return {
        "changed_files": changed,
        "disallowed_files": disallowed,
        "git_diff_check_passed": diff_check.returncode == 0,
        "head_unchanged": head_unchanged,
        "passed": not disallowed and diff_check.returncode == 0 and head_unchanged,
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _read_single(parent: Path, name: str) -> dict[str, Any]:
    candidates = list(parent.glob(f"*/{name}"))
    if len(candidates) != 1:
        raise RuntimeError(f"Expected one {name}, found {len(candidates)}.")
    result = json.loads(candidates[0].read_text(encoding="utf-8"))
    if not isinstance(result, dict):
        raise TypeError(f"Invalid {name}.")
    return result


def retrieval_hit_rank(changed_files: list[str], retrieval_paths: list[str]) -> int | None:
    """Return the one-based rank of the first changed file retrieved, if any."""

    ranks = [
        retrieval_paths.index(path) + 1
        for path in changed_files
        if path in retrieval_paths
    ]
    return min(ranks) if ranks else None


def retrieval_file_recall(reference_files: list[str], retrieval_paths: list[str]) -> float | None:
    """Return reference-file coverage in the retrieval top-k list."""

    expected = {path.replace("\\", "/").casefold() for path in reference_files}
    if not expected:
        return None
    retrieved = {path.replace("\\", "/").casefold() for path in retrieval_paths}
    return len(expected & retrieved) / len(expected)


def run_case(
    *,
    project_root: Path,
    task_path: Path,
    task: TaskSpec,
    source_repo: Path,
    config: EvaluationConfig,
    case_dir: Path,
    acceptance_path: Path | None = None,
    reference_fix_files: tuple[str, ...] = (),
    case_timeout: float = 600,
    test_timeout: float = 120,
) -> dict[str, Any]:
    """Persist one case even on infrastructure error; never overwrite prior cases."""
    started = time.perf_counter()
    if case_dir.exists():
        raise ValueError(f"Refusing to reuse existing case: {case_dir}")
    case_dir.mkdir(parents=True)
    workspace = case_dir / "workspace"
    record: dict[str, Any] = {
        "task_id": task.task_id,
        "difficulty": task.difficulty,
        "task_family": task.task_family,
        "config": config.name,
        "configuration": asdict(config),
        "case_dir": str(case_dir),
        "source_repository": str(source_repo),
        "initial_commit": task.initial_commit,
        "reference_fix_files": list(reference_fix_files),
        "evaluation_outcome": "infra_error",
        "terminal_state": None,
        "acceptance_passed": None,
        "steps": None,
        "retry_count": None,
        "token_usage": None,
        "metrics": None,
    }
    try:
        if not task.initial_commit:
            raise ValueError("Evaluation requires TaskSpec.initial_commit.")
        acceptance_path = (
            acceptance_path or (task_path.parent / str(task.acceptance_test_file)).resolve()
        )
        if not acceptance_path.is_file() or acceptance_path.is_relative_to(source_repo):
            raise ValueError("Acceptance test must exist outside source repository.")
        acceptance_digest = hashlib.sha256(acceptance_path.read_bytes()).hexdigest()
        record["acceptance_sha256"] = acceptance_digest
        source_commit = _git(["rev-parse", "HEAD"], cwd=project_root)
        git_root = _git(["rev-parse", "--show-toplevel"], cwd=project_root)
        record["codepilot_git_commit"] = (
            source_commit.stdout.strip()
            if source_commit.returncode == 0
            and git_root.returncode == 0
            and Path(git_root.stdout.strip()).resolve() == project_root.resolve()
            else None
        )
        _clone_baseline(source_repo, workspace, task.initial_commit)
        baseline = _visible_test(task, workspace, test_timeout)
        _write_json(case_dir / "baseline_visible_test.json", baseline)
        baseline_acceptance = _acceptance(acceptance_path, workspace, test_timeout)
        _write_json(case_dir / "baseline_acceptance.json", baseline_acceptance)
        record["baseline_test_return_code"] = baseline["return_code"]
        record["baseline_acceptance_return_code"] = baseline_acceptance["return_code"]
        if not _failed_test(baseline) or not _failed_test(baseline_acceptance):
            record["evaluation_outcome"] = "invalid_baseline"
            record["error"] = (
                "Baseline must fail both visible and acceptance tests with real test failures."
            )
        else:
            isolated_task = materialize_task_file(task, case_dir / "task.json")
            artifacts = case_dir / "codepilot_artifacts"
            command = [
                sys.executable,
                "-m",
                "codepilot.cli.main",
                "--task-file",
                str(isolated_task),
                "--artifacts-dir",
                str(artifacts),
                *config.cli_arguments(),
            ]
            env = dict(os.environ)
            env["PYTHONPATH"] = str(project_root / "src")
            env["PYTHONIOENCODING"] = "utf-8"
            completed = _process(command, cwd=project_root, timeout=case_timeout, env=env)
            (case_dir / "cli_stdout.txt").write_text(completed["stdout"], encoding="utf-8")
            (case_dir / "cli_stderr.txt").write_text(completed["stderr"], encoding="utf-8")
            record["cli_return_code"] = completed["return_code"]
            record["cli_elapsed_ms"] = completed["duration_ms"]
            record["cli_timed_out"] = completed["timed_out"]
            acceptance = _acceptance(acceptance_path, workspace, test_timeout)
            _write_json(case_dir / "acceptance_result.json", acceptance)
            record["acceptance_passed"] = (
                acceptance["return_code"] == 0 and not acceptance["timed_out"]
            )
            record["acceptance_infra_error"] = acceptance["timed_out"] or acceptance[
                "return_code"
            ] not in {0, 1}
            record["acceptance_unchanged"] = (
                hashlib.sha256(acceptance_path.read_bytes()).hexdigest() == acceptance_digest
            )
            audit = audit_workspace(workspace, task)
            record.update(audit)
            record["audit_passed"] = audit["passed"] and record["acceptance_unchanged"]
            record.pop("passed", None)
            (case_dir / "changes.diff").write_text(
                _checked_git(["diff", task.initial_commit, "--binary"], cwd=workspace),
                encoding="utf-8",
            )
            if completed["timed_out"]:
                record["evaluation_outcome"] = "timeout"
            else:
                summary = _read_single(artifacts, "final_summary.json")
                metadata = _read_single(artifacts, "run_metadata.json")
                for key in (
                    "terminal_state",
                    "verification_passed",
                    "steps",
                    "retry_count",
                    "plan_version",
                    "plan_noop_count",
                    "verified_at_step_limit",
                    "token_usage",
                    "metrics",
                    "retrieval_paths",
                    "artifact_dir",
                ):
                    record[key] = summary.get(key)
                record["retrieval_hit_rank"] = retrieval_hit_rank(
                    list(record.get("changed_files") or []),
                    list(record.get("retrieval_paths") or []),
                )
                record["retrieval_reference_hit_rank"] = retrieval_hit_rank(
                    list(reference_fix_files),
                    list(record.get("retrieval_paths") or []),
                )
                record["retrieval_reference_file_recall"] = retrieval_file_recall(
                    list(reference_fix_files),
                    list(record.get("retrieval_paths") or []),
                )
                safe_fields = {
                    "provider",
                    "model",
                    "base_url_identifier",
                    "temperature",
                    "max_output_tokens",
                    "agent_max_steps",
                    "agent_max_retries",
                    "tool_policy_version",
                    "prompt_version",
                    "planning_enabled",
                    "planning_mode",
                    "requires_reproduction",
                    "retrieval_mode",
                    "retrieval_top_k",
                    "context_mode",
                    "agent_context_trigger_chars",
                    "agent_context_max_chars",
                    "agent_context_recent_steps",
                    "command_timeout_seconds",
                    "git_commit",
                    "start_time",
                    "llm_request_retries",
                }
                record["run_metadata"] = {
                    key: metadata[key] for key in safe_fields if key in metadata
                }
                success = (
                    completed["return_code"] == 0
                    and summary.get("terminal_state") == "verified_success"
                    and summary.get("verification_passed") is True
                    and record["acceptance_passed"]
                    and record["audit_passed"]
                )
                record["evaluation_outcome"] = (
                    "infra_error"
                    if record["acceptance_infra_error"]
                    else "success"
                    if success
                    else "failed"
                )
                record["failure_reasons"] = [
                    label
                    for label, failed in (
                        ("cli_nonzero", completed["return_code"] != 0),
                        (
                            f"harness_{summary.get('terminal_state')}",
                            summary.get("terminal_state") != "verified_success",
                        ),
                        (
                            "visible_verification_failed",
                            summary.get("verification_passed") is not True,
                        ),
                        ("external_acceptance_failed", not record["acceptance_passed"]),
                        ("file_audit_failed", not record["audit_passed"]),
                    )
                    if failed
                ]
    except (OSError, RuntimeError, ValueError, TypeError, subprocess.SubprocessError) as error:
        record["error"] = f"{type(error).__name__}: {error}"
    record["evaluation_elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    _write_json(case_dir / "result.json", record)
    return record


def aggregate_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(str(record["config"]), []).append(record)
    by_config: dict[str, dict[str, Any]] = {}
    for name, group in grouped.items():
        successes = sum(record.get("evaluation_outcome") == "success" for record in group)
        accepted = sum(record.get("acceptance_passed") is True for record in group)
        values: dict[str, Any] = {
            "runs": len(group),
            "successes": successes,
            "success_rate": successes / len(group),
            "test_passes": accepted,
            "test_pass_rate": accepted / len(group),
            "verified_successes": sum(r.get("terminal_state") == "verified_success" for r in group),
            "infra_errors": sum(r.get("evaluation_outcome") == "infra_error" for r in group),
            "step_limit_successes": sum(
                record.get("verified_at_step_limit") is True for record in group
            ),
        }
        for output, path in {
            "steps": ("steps",),
            "retry_count": ("retry_count",),
            "input_tokens": ("token_usage", "input_tokens"),
            "output_tokens": ("token_usage", "output_tokens"),
            "total_tokens": ("token_usage", "total_tokens"),
            "run_elapsed_ms": ("metrics", "run_elapsed_ms"),
            "llm_latency_ms": ("metrics", "llm_latency_ms"),
            "tool_error_count": ("metrics", "tool_error_count"),
            "tool_denied_count": ("metrics", "tool_denied_count"),
            "tool_call_count": ("metrics", "tool_call_count"),
            "list_files_count": ("metrics", "list_files_count"),
            "read_file_count": ("metrics", "read_file_count"),
            "search_text_count": ("metrics", "search_text_count"),
            "bash_count": ("metrics", "bash_count"),
            "update_plan_count": ("metrics", "update_plan_count"),
            "plan_noop_count": ("metrics", "plan_noop_count"),
            "context_compaction_count": ("metrics", "context_compaction_count"),
            "context_request_count": ("metrics", "context_request_count"),
            "total_context_chars_sent": ("metrics", "total_context_chars_sent"),
            "context_chars_saved": ("metrics", "context_chars_saved"),
            "max_context_chars_before": ("metrics", "max_context_chars_before"),
            "max_context_chars_after": ("metrics", "max_context_chars_after"),
            "max_context_messages_sent": ("metrics", "max_context_messages_sent"),
            "max_context_steps_compacted": ("metrics", "max_context_steps_compacted"),
        }.items():
            samples = []
            for record in group:
                item: Any = record
                for key in path:
                    item = item.get(key) if isinstance(item, dict) else None
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    samples.append(item)
            values[f"avg_{output}"] = sum(samples) / len(samples) if samples else None
            values[f"{output}_samples"] = len(samples)
            totals = {
                "tool_error_count": "tool_errors",
                "tool_denied_count": "tool_denied",
                "plan_noop_count": "plan_noops",
                "context_compaction_count": "context_compactions",
            }
            if output in totals:
                values[totals[output]] = sum(samples) if samples else None
        retrieval_records = [
            record
            for record in group
            if (record.get("configuration") or {}).get("retrieval_mode") == "lexical"
        ]
        ranks = [
            record.get("retrieval_hit_rank")
            if "retrieval_hit_rank" in record
            else retrieval_hit_rank(
                list(record.get("changed_files") or []),
                list(record.get("retrieval_paths") or []),
            )
            for record in retrieval_records
        ]
        values["retrieval_samples"] = len(retrieval_records)
        values["retrieval_hit_at_1"] = sum(rank == 1 for rank in ranks)
        values["retrieval_hit_at_3"] = sum(
            isinstance(rank, int) and rank <= 3 for rank in ranks
        )
        values["retrieval_hit_at_1_rate"] = (
            values["retrieval_hit_at_1"] / len(retrieval_records)
            if retrieval_records
            else None
        )
        values["retrieval_hit_at_3_rate"] = (
            values["retrieval_hit_at_3"] / len(retrieval_records)
            if retrieval_records
            else None
        )
        reference_records = [
            record for record in retrieval_records if record.get("reference_fix_files")
        ]
        reference_ranks = [
            record.get("retrieval_reference_hit_rank")
            if "retrieval_reference_hit_rank" in record
            else retrieval_hit_rank(
                list(record.get("reference_fix_files") or []),
                list(record.get("retrieval_paths") or []),
            )
            for record in reference_records
        ]
        reference_recalls = [
            record.get("retrieval_reference_file_recall")
            if "retrieval_reference_file_recall" in record
            else retrieval_file_recall(
                list(record.get("reference_fix_files") or []),
                list(record.get("retrieval_paths") or []),
            )
            for record in reference_records
        ]
        values["retrieval_reference_samples"] = len(reference_records)
        values["retrieval_reference_hit_at_1_rate"] = (
            sum(rank == 1 for rank in reference_ranks) / len(reference_records)
            if reference_records
            else None
        )
        values["avg_retrieval_reference_file_recall"] = (
            sum(recall for recall in reference_recalls if recall is not None)
            / len([recall for recall in reference_recalls if recall is not None])
            if any(recall is not None for recall in reference_recalls)
            else None
        )
        by_config[name] = values
    return {"run_count": len(records), "by_config": by_config, "records": records}


def evaluation_schedule(
    prepared: list[PreparedTask], configs: list[str], repeat: int
) -> list[tuple[PreparedTask, str, int]]:
    """Return a deterministic rotated order to reduce first-arm ordering bias."""

    schedule: list[tuple[PreparedTask, str, int]] = []
    for task_index, item in enumerate(prepared):
        for repeat_index in range(1, repeat + 1):
            offset = (task_index + repeat_index - 1) % len(configs)
            ordered = configs[offset:] + configs[:offset]
            schedule.extend((item, name, repeat_index) for name in ordered)
    return schedule


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.repeat < 1 or args.case_timeout <= 0 or args.test_timeout <= 0:
            raise ValueError("Repeat and timeout values must be positive.")
        configs = args.config or list(DEFAULT_CONFIGS)
        if len(configs) != len(set(configs)):
            raise ValueError("Duplicate configurations are not allowed.")
        prepared = prepare_tasks(args.task_file, args.suite)
        plan = {
            "tasks": [p.task.task_id for p in prepared],
            "configs": configs,
            "repeat": args.repeat,
            "cases": len(prepared) * len(configs) * args.repeat,
            "ordering": "deterministic_rotating_counterbalance",
        }
        if args.list or args.dry_run:
            print(json.dumps(plan, indent=2, ensure_ascii=False))
            return 0
        project_root = Path(__file__).resolve().parents[3]
        load_dotenv(
            Path(os.getenv("CODEPILOT_ENV_FILE", str(project_root / ".env"))), override=False
        )
        Settings.from_env()
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        output = (args.output_dir or project_root / "artifacts" / "evaluations" / stamp).resolve()
        if output.exists():
            raise ValueError(f"Output directory already exists: {output}")
        output.mkdir(parents=True)
        records: list[dict[str, Any]] = []
        for item, name, index in evaluation_schedule(prepared, configs, args.repeat):
            print(f"Running {item.task.task_id} / {name} / {index}", flush=True)
            record = run_case(
                project_root=project_root,
                task_path=item.path,
                task=item.task,
                source_repo=item.source_repo,
                acceptance_path=item.acceptance_path,
                reference_fix_files=item.reference_fix_files,
                config=ALL_CONFIGS[name],
                case_dir=output / item.task.task_id / name / f"run-{index:02d}",
                case_timeout=args.case_timeout,
                test_timeout=args.test_timeout,
            )
            records.append(record)
            summary = {
                "created_at": datetime.now(UTC).isoformat(),
                **plan,
                **aggregate_records(records),
            }
            _write_json(output / "evaluation_summary.json", summary)
            from codepilot.evaluation.report import write_reports

            write_reports(summary, output)
        print(f"evaluation_dir={output}")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"Evaluation failed: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
