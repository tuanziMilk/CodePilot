"""Offline scripted demonstration of the real tools, loop, and verifier.

This exercises engineering behavior. It does not evaluate an LLM or provide
evidence of live-model task success, token cost, or retrieval performance.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import uuid
from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from codepilot.agent.harness import AgentHarness, TerminalState
from codepilot.environment.git_bash import GitBashEnvironment
from codepilot.environment.workspace import Workspace
from codepilot.llm.base import LLMProvider, ProviderError
from codepilot.models.messages import ChatRequest, ChatResponse, Message, MessageRole
from codepilot.models.protocol import ToolCall
from codepilot.permissions.policy import PermissionPolicy
from codepilot.tools.base import ToolContext
from codepilot.tools.bash import BashTool
from codepilot.tools.dispatcher import ToolDispatcher
from codepilot.tools.file_tools import EditFileTool, ReadFileTool
from codepilot.tools.plan import UpdatePlanTool
from codepilot.trajectory.writer import RunMetadata, TrajectoryWriter
from codepilot.verification.runner import VerificationRunner

TEST_COMMAND = "python -m pytest test_calculator.py -q"


def _call(call_id: str, name: str, **arguments: object) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        tool_calls=(ToolCall(call_id=call_id, name=name, arguments=arguments),),
    )


class ScriptedDemoProvider(LLMProvider):
    """Return a fixed sequence of public actions; no model or network is used."""

    def __init__(self) -> None:
        self._responses = deque(
            [
                _call("plan", "update_plan", steps=["Inspect", "Reproduce", "Fix", "Verify"]),
                _call("source", "read_file", path="calculator.py"),
                _call("test", "read_file", path="test_calculator.py"),
                _call("reproduce", "bash", command=TEST_COMMAND),
                _call(
                    "fix",
                    "edit_file",
                    path="calculator.py",
                    old_text="return a - b",
                    new_text="return a + b",
                ),
                _call("test-fix", "bash", command=TEST_COMMAND),
                Message(role=MessageRole.ASSISTANT, content="Ready for external verification."),
            ]
        )

    def complete(self, request: ChatRequest) -> ChatResponse:
        if not self._responses:
            raise ProviderError("The offline demonstration exhausted its scripted actions.")
        return ChatResponse(message=self._responses.popleft(), latency_ms=0)


def _find_bash(explicit: Path | None) -> Path:
    candidates = [explicit] if explicit else [
        Path(os.environ["GIT_BASH_PATH"]) if os.environ.get("GIT_BASH_PATH") else None,
        Path(r"E:\Git\bin\bash.exe"),
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(shutil.which("bash")) if shutil.which("bash") else None,
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate.resolve()
    raise ValueError("Git Bash was not found; pass --bash-path with the full executable path.")


def run_demo(output_parent: Path, bash_path: Path) -> dict[str, object]:
    """Create a fresh tiny buggy workspace and preserve its real execution artifacts."""

    run_id = f"scripted-{uuid.uuid4().hex[:12]}"
    demo_dir = output_parent.resolve() / run_id
    workspace_dir = demo_dir / "workspace"
    workspace_dir.mkdir(parents=True, exist_ok=False)
    (workspace_dir / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8"
    )
    (workspace_dir / "test_calculator.py").write_text(
        "from calculator import add\n\n"
        "def test_add() -> None:\n    assert add(2, 3) == 5\n", encoding="utf-8"
    )
    workspace = Workspace(workspace_dir, allowed_write_paths=frozenset({"calculator.py"}))
    environment = GitBashEnvironment(workspace.root, bash_path)
    policy = PermissionPolicy("mvp-v1", workspace=workspace)
    dispatcher = ToolDispatcher(
        [UpdatePlanTool(), ReadFileTool(), EditFileTool(), BashTool()],
        ToolContext(workspace, environment, policy, command_timeout_seconds=30),
    )
    trajectory = TrajectoryWriter(
        demo_dir / "run",
        RunMetadata(
            run_id=run_id,
            task_id="offline-scripted-addition-demo",
            provider="scripted-offline",
            model="fixed-actions-no-llm",
            base_url_identifier="none",
            temperature=0,
            max_output_tokens=1,
            llm_request_retries=0,
            agent_max_steps=8,
            agent_max_retries=0,
            tool_policy_version="mvp-v1",
            prompt_version="mvp-v2",
            planning_enabled=True,
            planning_mode="required",
            requires_reproduction=True,
            start_time=datetime.now(UTC),
        ),
    )
    result = AgentHarness(
        ScriptedDemoProvider(), dispatcher,
        VerificationRunner(environment, policy, timeout_seconds=30), trajectory,
        temperature=0, max_output_tokens=1, max_steps=8, max_retries=0,
        planning_mode="required",
    ).run("Correct integer addition.", TEST_COMMAND, requires_reproduction=True)
    summary = {
        "run_id": run_id,
        "demo_mode": "scripted_offline_not_model_evaluation",
        "terminal_state": result.terminal_state.value,
        "verification_passed": result.verification.passed if result.verification else None,
        "reproduction_failure_observed": result.state.reproduction_failure_observed,
        "steps": result.state.step,
        "token_usage": result.state.aggregate_usage.model_dump(),
        "metrics": trajectory.metrics(),
        "workspace": str(workspace.root),
        "artifact_dir": str(trajectory.artifact_dir),
    }
    trajectory.write_final_summary(summary)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the offline scripted CodePilot demo (no API key).")
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/demos"))
    parser.add_argument("--bash-path", type=Path)
    args = parser.parse_args()
    try:
        summary = run_demo(args.output_dir, _find_bash(args.bash_path))
    except (OSError, ValueError) as error:
        parser.error(str(error))
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["terminal_state"] == TerminalState.VERIFIED_SUCCESS.value else 1


if __name__ == "__main__":
    raise SystemExit(main())
