"""Generate local Git baselines without a model/API or global Git configuration."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

from codepilot.benchmarks.definitions import BenchmarkTask, task_definitions


def git(repo: Path, *args: str) -> str:
    environment = os.environ.copy()
    environment.update({
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_AUTHOR_NAME": "CodePilot Benchmark",
        "GIT_COMMITTER_NAME": "CodePilot Benchmark",
        "GIT_AUTHOR_EMAIL": "benchmark@codepilot.invalid",
        "GIT_COMMITTER_EMAIL": "benchmark@codepilot.invalid",
    })
    result = subprocess.run(
        ["git", "-c", "user.name=CodePilot Benchmark", "-c",
         "user.email=benchmark@codepilot.invalid", "-c", "core.autocrlf=false", "-c",
         "commit.gpgsign=false", *args],
        cwd=repo, env=environment, text=True, capture_output=True, check=True,
    )
    return result.stdout.strip()


def baseline_files(task: BenchmarkTask) -> dict[str, str]:
    return {
        **task.files,
        "test_behavior.py": task.visible_test,
        ".gitignore": ".codepilot/\n__pycache__/\n.pytest_cache/\n*.pyc\n",
        "README.md": f"# {task.task_id}\n\nRun visible tests: `python -m pytest -q`.\n",
    }


def definition_digest(files: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()


def prepare_suite(root: Path) -> dict:
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    manifest = {"tasks": []}
    challenge_manifest = {"tasks": []}
    commits = {}
    for task in task_definitions():
        files = baseline_files(task)
        repo = root / "repos" / task.task_id
        spec_path = root / "tasks" / f"{task.task_id}.json"
        if repo.exists():
            if not (repo / ".git").is_dir():
                raise ValueError(f"Refusing to modify an existing non-benchmark directory: {repo}")
            if not spec_path.is_file():
                raise ValueError(f"Existing baseline has no TaskSpec; inspect it manually: {repo}")
            previous = json.loads(spec_path.read_text(encoding="utf-8"))
            head = git(repo, "rev-parse", "HEAD")
            if head != previous.get("initial_commit") or git(repo, "status", "--porcelain"):
                raise ValueError(f"Existing baseline has changes; refusing to overwrite: {repo}")
            tracked = set(git(repo, "ls-files").splitlines())
            if tracked != set(files) or any(
                (repo / path).read_text(encoding="utf-8") != content
                for path, content in files.items()
            ):
                raise ValueError(f"Baseline definition changed; use a new output directory: {repo}")
            commit = head
        else:
            repo.mkdir(parents=True)
            for relative, content in files.items():
                target = repo / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content, encoding="utf-8", newline="\n")
            git(repo, "init", "--initial-branch=baseline", "--object-format=sha1")
            git(repo, "add", ".")
            git(repo, "commit", "-m", f"Buggy baseline: {task.task_id}")
            commit = git(repo, "rev-parse", "HEAD")

        acceptance = root / "acceptance" / f"{task.task_id.replace('-', '_')}_test.py"
        acceptance.parent.mkdir(parents=True, exist_ok=True)
        acceptance.write_text(task.acceptance_test, encoding="utf-8", newline="\n")
        reference = root / "reference" / f"{task.task_id}.json"
        reference.parent.mkdir(parents=True, exist_ok=True)
        reference.write_text(json.dumps({
            "task_id": task.task_id, "path": task.fix_path,
            "old": task.old, "new": task.new,
            "baseline_definition_sha256": definition_digest(files),
        }, indent=2) + "\n", encoding="utf-8", newline="\n")
        spec = {
            "task_id": task.task_id,
            "repository": f"../repos/{task.task_id}",
            "issue_description": task.issue,
            "verification_command": "python -m pytest -q",
            "allowed_files": sorted(task.files),
            "visible_tests": ["test_behavior.py"],
            "forbidden_files": ["test_behavior.py", "README.md", ".gitignore"],
            "success_condition": "Visible tests and independent external acceptance tests pass.",
            "initial_commit": commit,
            "requires_reproduction": True,
            "acceptance_test_file": f"../acceptance/{acceptance.name}",
            "difficulty": task.difficulty,
            "task_family": task.family,
        }
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_text(json.dumps(spec, indent=2) + "\n", encoding="utf-8", newline="\n")
        manifest["tasks"].append(f"tasks/{task.task_id}.json")
        if task.difficulty == "challenge":
            challenge_manifest["tasks"].append(f"tasks/{task.task_id}.json")
        commits[task.task_id] = commit
    (root / "suite.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    (root / "challenge_suite.json").write_text(
        json.dumps(challenge_manifest, indent=2) + "\n", encoding="utf-8", newline="\n",
    )
    return {
        "suite": str(root / "suite.json"),
        "challenge_suite": str(root / "challenge_suite.json"),
        "task_count": len(commits),
        "commits": commits,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("benchmarks"))
    args = parser.parse_args()
    try:
        print(json.dumps(prepare_suite(args.output), indent=2))
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"Benchmark preparation failed: {error}\n")


if __name__ == "__main__":
    main()
