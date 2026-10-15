import json
from datetime import UTC, datetime
from types import SimpleNamespace

from codepilot.agent.harness import AgentHarness, TerminalState
from codepilot.models.messages import ChatResponse, Message, MessageRole
from codepilot.models.protocol import ToolCall
from codepilot.tools.dispatcher import ToolDispatcher
from codepilot.tools.plan import UpdatePlanTool
from codepilot.trajectory.writer import RunMetadata, TrajectoryWriter
from codepilot.verification.runner import VerificationResult


def test_planning_off_hides_schema_denies_spoofed_call_and_exposes_test_command(tmp_path) -> None:
    requests = []
    responses = iter([
        Message(role=MessageRole.ASSISTANT, tool_calls=(
            ToolCall(call_id="unexpected-plan", name="update_plan", arguments={"steps": ["Inspect"]}),
        )),
        Message(role=MessageRole.ASSISTANT, content="Ready."),
    ])

    def complete(request):
        requests.append(request)
        return ChatResponse(message=next(responses), latency_ms=1)

    trajectory = TrajectoryWriter(tmp_path / "run", RunMetadata(
        run_id="off", provider="scripted", model="scripted", base_url_identifier="none",
        temperature=0, max_output_tokens=100, llm_request_retries=0, agent_max_steps=3,
        agent_max_retries=0, tool_policy_version="test", prompt_version="test",
        start_time=datetime.now(UTC), planning_mode="off",
    ))
    harness = AgentHarness(
        SimpleNamespace(complete=complete),
        ToolDispatcher([UpdatePlanTool()], SimpleNamespace()),
        SimpleNamespace(verify=lambda command: VerificationResult(True, command, "1 passed", 0, 1)),
        trajectory, temperature=0, max_output_tokens=100, max_steps=3, max_retries=0,
        planning_mode="off",
    )
    command = "python -m pytest test_feature.py -q"
    result = harness.run("Fix the behavior.", command)

    assert result.terminal_state is TerminalState.VERIFIED_SUCCESS
    assert result.state.plan_version == 0
    assert all(tool.name != "update_plan" for request in requests for tool in request.tools)
    assert command in requests[0].messages[0].content
    observations = [message.content for message in requests[1].messages if message.role is MessageRole.TOOL]
    assert any("Planning is disabled" in observation for observation in observations)
    events = [json.loads(line) for line in (tmp_path / "run/trajectory.jsonl").read_text().splitlines()]
    assert any(event["state_change"] == "tool_denied" for event in events)
