from codepilot.agent.context import PublicRunSnapshot, ReActContextManager
from codepilot.models.messages import Message, MessageRole, tool_observation
from codepilot.models.protocol import ToolCall, ToolResult, ToolStatus


def test_compaction_keeps_pinned_messages_and_recent_protocol_pairs() -> None:
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="task"),
    ]
    for index in range(5):
        call = ToolCall(
            call_id=str(index),
            name="read_file",
            arguments={"path": f"source_{index}.py"},
        )
        messages.extend(
            [
                Message(
                    role=MessageRole.ASSISTANT,
                    content=f"private-looking free text {index}",
                    tool_calls=(call,),
                ),
                tool_observation(
                    ToolResult(
                        call_id=str(index),
                        tool_name="read_file",
                        status=ToolStatus.OK,
                        output_summary=(f"content-{index} " * 120),
                        duration_ms=1,
                    )
                ),
            ]
        )

    view = ReActContextManager(
        trigger_chars=4_000, max_chars=32_000, recent_steps=2
    ).build(
        messages,
        pinned_count=2,
        snapshot=PublicRunSnapshot(
            plan_steps=("Inspect", "Fix"),
            reproduction_failure_observed=True,
        ),
    )

    assert view.compacted
    assert view.compacted_steps == 3
    assert view.messages[:2] == tuple(messages[:2])
    summary = view.messages[2]
    assert summary.role is MessageRole.USER
    assert "observable tool calls and results" in summary.content
    assert "read_file(source_0.py)" in summary.content
    assert "failed test reproduced=yes" in summary.content
    assert "private-looking free text" not in summary.content
    assert [message.tool_call_id for message in view.messages if message.role is MessageRole.TOOL] == [
        "3",
        "4",
    ]


def test_character_budget_compacts_complete_older_steps() -> None:
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="task"),
    ]
    for index in range(3):
        call = ToolCall(call_id=str(index), name="read_file", arguments={"path": f"{index}.py"})
        messages.extend(
            [
                Message(role=MessageRole.ASSISTANT, tool_calls=(call,)),
                Message(
                    role=MessageRole.TOOL,
                    content="x" * 2_000,
                    tool_call_id=str(index),
                ),
            ]
        )

    view = ReActContextManager(
        trigger_chars=4_000, max_chars=4_000, recent_steps=3
    ).build(
        messages,
        pinned_count=2,
        snapshot=PublicRunSnapshot(),
    )

    assert view.compacted_steps == 2
    assert view.selected_chars < view.original_chars
    assert view.messages[-2].tool_calls[0].call_id == "2"
    assert view.messages[-1].tool_call_id == "2"


def test_full_context_mode_preserves_complete_history() -> None:
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="task"),
        Message(role=MessageRole.ASSISTANT, content="done"),
    ]

    view = ReActContextManager(
        mode="full", trigger_chars=4_000, max_chars=4_000, recent_steps=1
    ).build(
        messages,
        pinned_count=2,
        snapshot=PublicRunSnapshot(),
    )

    assert view.messages == tuple(messages)
    assert not view.compacted


def test_compact_mode_preserves_short_history_below_trigger() -> None:
    messages = [
        Message(role=MessageRole.SYSTEM, content="system"),
        Message(role=MessageRole.USER, content="task"),
    ]
    for index in range(5):
        call = ToolCall(call_id=str(index), name="read_file", arguments={"path": f"{index}.py"})
        messages.extend(
            [
                Message(role=MessageRole.ASSISTANT, tool_calls=(call,)),
                Message(
                    role=MessageRole.TOOL,
                    content="small observation",
                    tool_call_id=str(index),
                ),
            ]
        )

    view = ReActContextManager(
        trigger_chars=16_000, max_chars=32_000, recent_steps=2
    ).build(
        messages,
        pinned_count=2,
        snapshot=PublicRunSnapshot(),
    )

    assert view.messages == tuple(messages)
    assert not view.compacted


def test_tool_observation_exposes_status_without_reasoning() -> None:
    result = ToolResult(
        call_id="call-1",
        tool_name="edit_file",
        status=ToolStatus.DENIED,
        output_summary="The requested path is not writable.",
        return_code=2,
        duration_ms=0,
    )

    observation = tool_observation(result)

    assert observation.role is MessageRole.TOOL
    assert observation.tool_call_id == "call-1"
    assert observation.content == (
        "Tool: edit_file\nStatus: denied\nReturn code: 2\nObservation:\n"
        "The requested path is not writable."
    )
