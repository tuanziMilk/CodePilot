"""CLI composition root.

This is the only module that wires concrete adapters together. The Harness
itself remains independent of settings, DeepSeek, and Windows paths.
"""

from __future__ import annotations

import argparse
import json
import uuid
from datetime import UTC, datetime
from pathlib import Path

from codepilot.agent.harness import AgentHarness
from codepilot.config.settings import Settings
from codepilot.environment.git_bash import GitBashEnvironment
from codepilot.environment.workspace import Workspace
from codepilot.llm.deepseek import OpenAICompatibleProvider
from codepilot.models.task import TaskSpecError, load_task_spec, resolve_task_repository
from codepilot.permissions.policy import PermissionPolicy
from codepilot.retrieval.lexical import LexicalRepositoryRetriever, RetrievalResult
from codepilot.tools.base import ToolContext
from codepilot.tools.bash import BashTool
from codepilot.tools.dispatcher import ToolDispatcher
from codepilot.tools.file_tools import EditFileTool, ListFilesTool, ReadFileTool, SearchTextTool
from codepilot.tools.plan import UpdatePlanTool
from codepilot.trajectory.writer import RunMetadata, TrajectoryEvent, TrajectoryWriter
from codepilot.verification.runner import VerificationRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a bounded CodePilot task.")
    parser.add_argument("--task", help="Natural-language task for direct/manual runs.")
    parser.add_argument(
        "--task-file",
        type=Path,
        help="TaskSpec JSON file for reproducible benchmark or evaluation runs.",
    )
    parser.add_argument("--workspace", type=Path, help="Repository the Agent may access.")
    parser.add_argument(
        "--verify-command",
        help="Explicit allow-listed test command used to decide success.",
    )
    parser.add_argument(
        "--artifacts-dir",
        type=Path,
        default=None,
        help="Optional artifact parent; defaults to WORKSPACE/.codepilot/runs.",
    )
    parser.add_argument(
        "--allowed-edit-path",
        action="append",
        default=None,
        help="Workspace-relative file the Agent may edit; repeat for multiple files.",
    )
    parser.add_argument(
        "--planning-mode",
        choices=("off", "optional", "required"),
        default=None,
        help="Hide planning entirely, expose it optionally, or require it before repository tools.",
    )
    parser.add_argument(
        "--require-plan",
        action="store_true",
        help="Require a short public update_plan call before repository tools.",
    )
    parser.add_argument(
        "--reproduction-policy",
        choices=("task", "on", "off"),
        default="task",
        help="Use the TaskSpec reproduction rule, force it on, or disable it for an evaluation arm.",
    )
    parser.add_argument(
        "--retrieval-mode",
        choices=("none", "lexical"),
        default="none",
        help="Optional repository context strategy; default is the no-retrieval baseline.",
    )
    parser.add_argument(
        "--retrieval-top-k",
        type=int,
        default=3,
        help="Maximum files supplied by lexical retrieval (1-10; default: 3).",
    )
    return parser


def resolve_run_input(
    args: argparse.Namespace,
) -> tuple[str, Path, str, frozenset[str], str | None, bool]:
    """Resolve direct CLI flags or a reproducible TaskSpec into one run input."""

    if args.task_file:
        if any((args.task, args.workspace, args.verify_command, args.allowed_edit_path)):
            raise ValueError("--task-file cannot be combined with direct task/workspace/verification flags.")
        task_path = args.task_file.resolve()
        task = load_task_spec(task_path)
        return (
            task.issue_description,
            resolve_task_repository(task_path, task),
            task.verification_command,
            frozenset(task.allowed_files),
            task.task_id,
            task.requires_reproduction,
        )

    if not all((args.task, args.workspace, args.verify_command, args.allowed_edit_path)):
        raise ValueError(
            "Direct runs require --task, --workspace, --verify-command, and --allowed-edit-path."
        )
    return (
        args.task,
        args.workspace.resolve(),
        args.verify_command,
        frozenset(args.allowed_edit_path),
        None,
        False,
    )


def resolve_reproduction_policy(policy: str, task_requires_reproduction: bool) -> bool:
    """Resolve an evaluation override without changing the TaskSpec itself."""

    if policy == "on":
        return True
    if policy == "off":
        return False
    return task_requires_reproduction


def resolve_planning_mode(mode: str | None, require_plan: bool) -> str:
    """Preserve the legacy flag while exposing a strict no-planning evaluation arm."""

    if require_plan and mode not in {None, "required"}:
        raise ValueError("--require-plan cannot be combined with --planning-mode off/optional.")
    return mode or ("required" if require_plan else "optional")


def main() -> int:
    args = build_parser().parse_args()
    if not 1 <= args.retrieval_top_k <= 10:
        build_parser().error("--retrieval-top-k must be between 1 and 10.")
    try:
        task_text, workspace_path, verify_command, allowed_files, task_id, task_requires_reproduction = (
            resolve_run_input(args)
        )
        planning_mode = resolve_planning_mode(args.planning_mode, args.require_plan)
        forbidden_files = (
            frozenset(load_task_spec(args.task_file.resolve()).forbidden_files)
            if args.task_file
            else frozenset()
        )
    except (TaskSpecError, ValueError) as error:
        build_parser().error(str(error))
    requires_reproduction = resolve_reproduction_policy(
        args.reproduction_policy,
        task_requires_reproduction,
    )

    try:
        settings = Settings.from_env()
    except ValueError:
        build_parser().error("Model configuration is missing or invalid. Check this project's .env file.")
    workspace = Workspace(
        workspace_path,
        allowed_write_paths=allowed_files,
        forbidden_write_paths=forbidden_files,
    )
    environment = GitBashEnvironment(workspace.root, settings.git_bash_path)
    policy = PermissionPolicy(settings.tool_policy_version, workspace=workspace)
    context = ToolContext(
        workspace=workspace,
        environment=environment,
        permissions=policy,
        command_timeout_seconds=settings.command_timeout_seconds,
    )
    tools = [ListFilesTool(), ReadFileTool(), SearchTextTool(), EditFileTool(), BashTool()]
    if planning_mode != "off":
        tools.insert(0, UpdatePlanTool())
    dispatcher = ToolDispatcher(
        tools,
        context,
    )
    run_id = uuid.uuid4().hex
    artifact_parent = args.artifacts_dir or workspace.root / ".codepilot" / "runs"
    metadata = RunMetadata(
        run_id=run_id,
        task_id=task_id,
        start_time=datetime.now(UTC),
        git_commit=environment.git_commit(),
        planning_enabled=planning_mode != "off",
        planning_mode=planning_mode,
        requires_reproduction=requires_reproduction,
        retrieval_mode=args.retrieval_mode,
        retrieval_top_k=args.retrieval_top_k if args.retrieval_mode != "none" else 0,
        **settings.redacted_snapshot(),
    )
    trajectory = TrajectoryWriter(artifact_parent / run_id, metadata)
    retrieval_result: RetrievalResult | None = None
    if args.retrieval_mode == "lexical":
        retrieval_result = LexicalRepositoryRetriever(
            workspace,
            top_k=args.retrieval_top_k,
        ).retrieve(task_text)
        trajectory.write_event(
            TrajectoryEvent(
                run_id=run_id,
                step=0,
                event_type="retrieval",
                action_summary="Retrieve lexical repository context.",
                action="retrieve_context",
                reason="Select bounded source excerpts relevant to the task before the first model call.",
                targets=list(retrieval_result.paths),
                tool_name="lexical_retrieval",
                tool_result_summary=(
                    f"Retrieved {len(retrieval_result.documents)} file(s): "
                    + ", ".join(retrieval_result.paths)
                    if retrieval_result.documents
                    else "No lexical repository matches found."
                ),
                state_change="retrieval_context_ready",
                latency_ms=retrieval_result.latency_ms,
            )
        )
    harness = AgentHarness(
        provider=OpenAICompatibleProvider(settings),
        dispatcher=dispatcher,
        verifier=VerificationRunner(environment, policy, settings.command_timeout_seconds),
        trajectory=trajectory,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        max_steps=settings.agent_max_steps,
        max_retries=settings.agent_max_retries,
        planning_mode=planning_mode,
    )
    result = harness.run(
        task_text,
        verify_command,
        requires_reproduction=requires_reproduction,
        retrieval_context=retrieval_result.context_message() if retrieval_result else None,
    )
    summary = {
        "run_id": run_id,
        "task_id": task_id,
        "terminal_state": result.terminal_state.value,
        "verification_passed": result.verification.passed if result.verification else None,
        "verification_failure_kind": (
            result.verification.failure_kind if result.verification else None
        ),
        "steps": result.state.step,
        "retry_count": result.state.repair_retry_count,
        "plan_version": result.state.plan_version,
        "plan_steps": result.state.plan_steps,
        "planning_mode": planning_mode,
        "retrieval_mode": args.retrieval_mode,
        "retrieval_paths": list(retrieval_result.paths) if retrieval_result else [],
        "token_usage": result.state.aggregate_usage.model_dump(),
        "metrics": trajectory.metrics(),
        "artifact_dir": str(trajectory.artifact_dir),
        "git_diff": environment.git_diff(),
    }
    trajectory.write_final_summary(summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if result.terminal_state.value == "verified_success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
