from __future__ import annotations

from collections import deque
from datetime import UTC, datetime
from pathlib import Path

from codepilot.agent.harness import AgentHarness, TerminalState
from codepilot.environment.git_bash import GitBashEnvironment
from codepilot.environment.workspace import Workspace
from codepilot.llm.base import LLMProvider
from codepilot.models.messages import ChatRequest, ChatResponse, Message, MessageRole
from codepilot.models.protocol import ToolCall
from codepilot.permissions.policy import PermissionPolicy
from codepilot.tools.base import ToolContext
from codepilot.tools.bash import BashTool
from codepilot.tools.dispatcher import ToolDispatcher
from codepilot.tools.file_tools import EditFileTool, ListFilesTool, ReadFileTool, SearchTextTool
from codepilot.tools.plan import UpdatePlanTool
from codepilot.trajectory.writer import RunMetadata, TrajectoryWriter
from codepilot.verification.runner import VerificationRunner


class ScriptedProvider(LLMProvider):
    def __init__(self) -> None:
        self._messages = deque(
            [
                _read("1"),
                _plan("2"),
                _bash("3"),
                _edit("4"),
                _bash("5"),
                _plan("6"),
                Message(role=MessageRole.ASSISTANT, content="Ready for verification."),
            ]
        )

    def complete(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(message=self._messages.popleft(), latency_ms=1)


def test_required_plan_is_recorded_before_repository_actions(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n",
        encoding="utf-8",
    )
    (tmp_path / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add() -> None:\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    workspace = Workspace(tmp_path, allowed_write_paths=frozenset({"calculator.py"}))
    environment = GitBashEnvironment(workspace.root, Path(r"E:\Git\bin\bash.exe"))
    policy = PermissionPolicy("test-v1")
    dispatcher = ToolDispatcher(
        [UpdatePlanTool(), ListFilesTool(), ReadFileTool(), SearchTextTool(), EditFileTool(), BashTool()],
        ToolContext(workspace, environment, policy, command_timeout_seconds=30),
    )
    trajectory = TrajectoryWriter(
        tmp_path / "artifacts" / "run",
        RunMetadata(
            run_id="run",
            provider="fake",
            model="scripted",
            base_url_identifier="none",
            temperature=0,
            max_output_tokens=100,
            llm_request_retries=0,
            agent_max_steps=8,
            agent_max_retries=0,
            tool_policy_version="test-v1",
            prompt_version="test-v1",
            planning_enabled=True,
            requires_reproduction=True,
            start_time=datetime.now(UTC),
        ),
    )
    harness = AgentHarness(
        ScriptedProvider(),
        dispatcher,
        VerificationRunner(environment, policy, timeout_seconds=30),
        trajectory,
        temperature=0,
        max_output_tokens=100,
        max_steps=8,
        max_retries=0,
        require_plan=True,
    )

    result = harness.run("Fix add.", "python -m pytest -q", requires_reproduction=True)

    assert result.terminal_state is TerminalState.VERIFIED_SUCCESS
    assert result.state.plan_version == 1
    assert result.state.plan_noop_count == 1
    assert result.state.plan_steps == ["Read source", "Run test", "Edit source", "Verify"]
    events = (trajectory.artifact_dir / "trajectory.jsonl").read_text(encoding="utf-8")
    assert "requires update_plan" in events
    assert "plan_version" in events
    assert "tool_plan_unchanged" in events
    assert "Do not repeat the same plan" in events


def _plan(call_id: str) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        tool_calls=(
            ToolCall(
                call_id=call_id,
                name="update_plan",
                arguments={"steps": ["Read source", "Run test", "Edit source", "Verify"]},
            ),
        ),
    )


def _read(call_id: str) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        tool_calls=(ToolCall(call_id=call_id, name="read_file", arguments={"path": "calculator.py"}),),
    )


def _bash(call_id: str) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        tool_calls=(
            ToolCall(call_id=call_id, name="bash", arguments={"command": "python -m pytest -q"}),
        ),
    )


def _edit(call_id: str) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        tool_calls=(
            ToolCall(
                call_id=call_id,
                name="edit_file",
                arguments={
                    "path": "calculator.py",
                    "old_text": "return a - b",
                    "new_text": "return a + b",
                },
            ),
        ),
    )
