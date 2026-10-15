"""Prove each task fails before its reference edit and passes afterward, without an API."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from codepilot.benchmarks.prepare import git
from codepilot.models.task import load_task_spec, resolve_task_repository


def run_tests(workspace: Path, acceptance: Path | None = None) -> dict:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(workspace)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    if acceptance is not None:
        command.extend([str(acceptance), "--confcutdir", str(acceptance.parent)])
    result = subprocess.run(
        command, cwd=workspace, env=environment, capture_output=True,
        text=True, timeout=60, check=False,
    )
    return {"return_code": result.returncode, "stdout": result.stdout, "stderr": result.stderr}


def apply_reference(workspace: Path, reference: dict) -> None:
    target = (workspace / reference["path"]).resolve()
    if not target.is_relative_to(workspace.resolve()):
        raise ValueError("Reference path escapes validation workspace")
    content = target.read_text(encoding="utf-8")
    if content.count(reference["old"]) != 1:
        raise ValueError("Reference edit requires exactly one original match")
    target.write_text(content.replace(reference["old"], reference["new"], 1),
                      encoding="utf-8", newline="\n")


def validate_suite(suite_path: Path, output: Path) -> dict:
    suite_path, output = suite_path.resolve(), output.resolve()
    if output.exists():
        raise ValueError(f"Choose a new validation output directory: {output}")
    task_paths = json.loads(suite_path.read_text(encoding="utf-8"))["tasks"]
    output.mkdir(parents=True)
    results = []
    for relative in task_paths:
        task_path = (suite_path.parent / relative).resolve()
        task = load_task_spec(task_path)
        if not task.initial_commit or not task.acceptance_test_file:
            raise ValueError(f"Task requires initial_commit and acceptance tests: {task.task_id}")
        repository = resolve_task_repository(task_path, task)
        acceptance = (task_path.parent / task.acceptance_test_file).resolve()
        if acceptance.is_relative_to(repository):
            raise ValueError("Acceptance tests must stay outside the agent repository")
        reference = json.loads(
            (suite_path.parent / "reference" / f"{task.task_id}.json").read_text(encoding="utf-8")
        )
        task_output = output / task.task_id
        task_output.mkdir()
        stage_results = {}
        for stage in ("baseline", "reference"):
            clone = task_output / stage
            git(repository.parent, "clone", "--no-hardlinks", str(repository), str(clone))
            git(clone, "checkout", "--detach", task.initial_commit)
            if stage == "reference":
                apply_reference(clone, reference)
            for category, test_file in (("visible", None), ("acceptance", acceptance)):
                result = run_tests(clone, test_file)
                stage_results[f"{stage}_{category}"] = result
                (task_output / f"{stage}_{category}.txt").write_text(
                    result["stdout"] + result["stderr"], encoding="utf-8",
                )
        baseline_failed = all(
            stage_results[f"baseline_{category}"]["return_code"] == 1
            and "failed" in stage_results[f"baseline_{category}"]["stdout"]
            for category in ("visible", "acceptance")
        )
        reference_passed = all(
            stage_results[f"reference_{category}"]["return_code"] == 0
            for category in ("visible", "acceptance")
        )
        clean_source = not git(repository, "status", "--porcelain")
        result = {
            "task_id": task.task_id,
            "difficulty": task.difficulty,
            "task_family": task.task_family,
            "initial_commit": task.initial_commit,
            "baseline_visible_failed": stage_results["baseline_visible"]["return_code"] == 1,
            "baseline_acceptance_failed": stage_results["baseline_acceptance"]["return_code"] == 1,
            "reference_visible_passed": stage_results["reference_visible"]["return_code"] == 0,
            "reference_acceptance_passed": stage_results["reference_acceptance"]["return_code"] == 0,
            "source_clean": clean_source,
            "validated": baseline_failed and reference_passed and clean_source,
        }
        results.append(result)
    report = {
        "suite": str(suite_path), "output_dir": str(output),
        "task_count": len(results),
        "validated_count": sum(result["validated"] for result in results),
        "all_validated": bool(results) and all(result["validated"] for result in results),
        "results": results,
    }
    (output / "validation_summary.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8",
    )
    rows = [
        "# Benchmark validation\n",
        "No model API was called. Acceptance tests remained outside every workspace.\n",
        "| Task | Difficulty | Baseline fails | Reference passes | Source clean | Validated |",
        "|---|---|---|---|---|---|",
    ]
    for result in results:
        rows.append(
            f"| {result['task_id']} | {result['difficulty']} | "
            f"{result['baseline_visible_failed'] and result['baseline_acceptance_failed']} | "
            f"{result['reference_visible_passed'] and result['reference_acceptance_passed']} | "
            f"{result['source_clean']} | {result['validated']} |"
        )
    (output / "validation_summary.md").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--suite", type=Path, default=Path("benchmarks/suite.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("artifacts/benchmark_validation") / datetime.now(
        UTC
    ).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        report = validate_suite(args.suite, output)
        print(json.dumps(report, indent=2))
        if not report["all_validated"]:
            parser.exit(1, "One or more benchmark validation checks failed.\n")
    except (ValueError, OSError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Benchmark validation failed: {error}\n")


if __name__ == "__main__":
    main()
