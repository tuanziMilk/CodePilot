from codepilot.models.protocol import ToolCall
from codepilot.trajectory.summaries import summarize_tool_calls, verification_summary


def test_summary_is_derived_from_observable_tool_call_data() -> None:
    summary = summarize_tool_calls(
        (
            ToolCall(
                call_id="call-1",
                name="edit_file",
                arguments={
                    "path": "calculator.py",
                    "old_text": "return a - b",
                    "new_text": "return a + b",
                },
            ),
        )
    )

    assert summary.action == "apply_minimal_edit"
    assert summary.targets == ("calculator.py",)
    assert "reasoning" not in summary.text.lower()


def test_verification_summary_is_harness_owned() -> None:
    summary = verification_summary("python -m pytest -q")

    assert summary.action == "verify_task"
    assert summary.targets == ("python -m pytest -q",)
    assert "Agent stopped requesting tools" in summary.reason
