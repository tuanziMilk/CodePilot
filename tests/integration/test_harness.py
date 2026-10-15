from __future__ import annotations

import json
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
    """Deterministic stand-in used to test the Harness rather than model quality."""

    def __init__(self) -> None:
        self._responses = deque(
            [
                Message(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            call_id="0",
                            name="bash",
                            arguments={"command": "rm -rf ."},
                        ),
                    ),
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(ToolCall(call_id="1", name="read_file", arguments={"path": "calculator.py"}),),
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            call_id="2",
                            name="bash",
                            arguments={"command": "python -m pytest -q"},
                        ),
                    ),
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            call_id="3",
                            name="edit_file",
                            arguments={
                                "path": "calculator.py",
                                "old_text": "return a - b",
                                "new_text": "return a + b",
                            },
                        ),
                    ),
                ),
                Message(
                    role=MessageRole.ASSISTANT,
                    tool_calls=(
                        ToolCall(
                            call_id="4",
                            name="bash",
                            arguments={"command": "python -m pytest -q"},
                        ),
                    ),
                ),
                Message(role=MessageRole.ASSISTANT, content="The fix is ready for verification."),
            ]
        )

    def complete(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(message=self._responses.popleft(), latency_ms=1)


def test_harness_requires_explicit_passing_verification(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text(
        "def add(a: int, b: int) -> int:\n    return a - b\n", encoding="utf-8"
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
        tmp_path / "artifacts" / "run-1",
        RunMetadata(
            run_id="run-1",
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
            start_time=datetime.now(UTC),
        ),
    )
    result = AgentHarness(
        ScriptedProvider(),
        dispatcher,
        VerificationRunner(environment, policy, timeout_seconds=30),
        trajectory,
        temperature=0,
        max_output_tokens=100,
        max_steps=8,
        max_retries=0,
    ).run("Fix the add function.", "python -m pytest -q")

    assert result.terminal_state is TerminalState.VERIFIED_SUCCESS
    assert result.verification and result.verification.passed
    assert "return a + b" in (tmp_path / "calculator.py").read_text(encoding="utf-8")
    trajectory_text = (tmp_path / "artifacts" / "run-1" / "trajectory.jsonl").read_text(
        encoding="utf-8"
    )
    assert "verification" in trajectory_text
    assert "verified_success" in trajectory_text
    assert "tool_denied" in trajectory_text
    events = [json.loads(line) for line in trajectory_text.splitlines()]
    assistant_events = [event for event in events if event["event_type"] == "assistant_response"]
    assert all(event["action_summary"] for event in assistant_events)
    assert assistant_events[0]["action"] == "run_command"
    assert assistant_events[3]["action"] == "apply_minimal_edit"
    assert assistant_events[-1]["action"] == "verify_task"
    assert assistant_events[-1]["action_summary"] != "The fix is ready for verification."
