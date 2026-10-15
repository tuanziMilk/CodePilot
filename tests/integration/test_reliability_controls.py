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
from codepilot.trajectory.writer import RunMetadata, TrajectoryWriter
from codepilot.verification.runner import VerificationRunner


class ScriptedProvider(LLMProvider):
    def __init__(self, messages: list[Message]) -> None:
        self._messages = deque(messages)

    def complete(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(message=self._messages.popleft(), latency_ms=1)


def test_bug_task_requires_failed_test_before_editing(tmp_path: Path) -> None:
    harness, trajectory = _harness(
        tmp_path,
        [
            _edit_call("1"),
            _bash_call("2", "python -m pytest -q"),
            _edit_call("3"),
            _bash_call("4", "python -m pytest -q"),
            Message(role=MessageRole.ASSISTANT, content="Ready for verification."),
        ],
        max_retries=0,
    )

    result = harness.run(
        "Fix add.",
        "python -m pytest -q",
        requires_reproduction=True,
    )

    assert result.terminal_state is TerminalState.VERIFIED_SUCCESS
    assert result.state.reproduction_failure_observed is True
    events = (trajectory.artifact_dir / "trajectory.jsonl").read_text(encoding="utf-8")
    assert "requires a failed allowed test reproduction" in events
    assert "tool_denied" in events


def test_verification_failure_returns_feedback_for_one_repair_retry(tmp_path: Path) -> None:
    harness, trajectory = _harness(
        tmp_path,
        [
            Message(role=MessageRole.ASSISTANT, content="Ready too early."),
            _edit_call("2"),
            Message(role=MessageRole.ASSISTANT, content="Ready now."),
        ],
        max_retries=1,
    )

    result = harness.run("Fix add.", "python -m pytest -q")

    assert result.terminal_state is TerminalState.VERIFIED_SUCCESS
    assert result.state.repair_retry_count == 1
    assert any("System verification feedback" in message.content for message in result.state.messages)
    events = (trajectory.artifact_dir / "trajectory.jsonl").read_text(encoding="utf-8")
    assert "verification_failed_retrying" in events


def _harness(
    tmp_path: Path,
    messages: list[Message],
    *,
    max_retries: int,
) -> tuple[AgentHarness, TrajectoryWriter]:
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
        [ListFilesTool(), ReadFileTool(), SearchTextTool(), EditFileTool(), BashTool()],
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
            agent_max_retries=max_retries,
            tool_policy_version="test-v1",
            prompt_version="test-v1",
            start_time=datetime.now(UTC),
        ),
    )
    return (
        AgentHarness(
            ScriptedProvider(messages),
            dispatcher,
            VerificationRunner(environment, policy, timeout_seconds=30),
            trajectory,
            temperature=0,
            max_output_tokens=100,
            max_steps=8,
            max_retries=max_retries,
        ),
        trajectory,
    )


def _edit_call(call_id: str) -> Message:
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


def _bash_call(call_id: str, command: str) -> Message:
    return Message(
        role=MessageRole.ASSISTANT,
        tool_calls=(ToolCall(call_id=call_id, name="bash", arguments={"command": command}),),
    )
