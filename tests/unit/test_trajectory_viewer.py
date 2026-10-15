import json
from pathlib import Path

from codepilot.trajectory.viewer import render_trajectory


def test_viewer_renders_new_and_legacy_events(tmp_path: Path) -> None:
    trajectory = tmp_path / "trajectory.jsonl"
    events = [
        {
            "step": 1,
            "event_type": "assistant_response",
            "action_summary": "Inspect repository files.",
            "action": "inspect_repository",
            "reason": "Discover the repository layout before selecting relevant files.",
            "targets": ["."],
        },
        {
            "step": 1,
            "event_type": "tool_result",
            "tool_name": "list_files",
            "tool_arguments": {},
            "tool_result_summary": "calculator.py\ntest_calculator.py",
            "state_change": "tool_ok",
        },
        {
            "step": 2,
            "event_type": "verification",
            "tool_result_summary": "1 passed",
            "state_change": "verified_success",
        },
    ]
    trajectory.write_text(
        "\n".join(json.dumps(event, indent=2) for event in events),
        encoding="utf-8",
    )

    rendered = render_trajectory(trajectory)

    assert "Step 1" in rendered
    assert "Action: Inspect repository files." in rendered
    assert "Tool: list_files" in rendered
    assert "Status: OK" in rendered
    assert "Verification" in rendered
    assert "Status: verified_success" in rendered


def test_viewer_renders_retrieval_event_as_retrieval_not_verification(tmp_path: Path) -> None:
    trajectory = tmp_path / "trajectory.jsonl"
    trajectory.write_text(
        json.dumps(
            {
                "step": 0,
                "event_type": "retrieval",
                "action_summary": "Retrieve lexical repository context.",
                "reason": "Select bounded source excerpts before the first model call.",
                "targets": ["src/result.py"],
                "tool_name": "lexical_retrieval",
                "tool_result_summary": "Retrieved 1 file(s): src/result.py",
                "state_change": "retrieval_context_ready",
                "latency_ms": 12,
            }
        ),
        encoding="utf-8",
    )

    rendered = render_trajectory(trajectory)

    assert "Action: Retrieve lexical repository context." in rendered
    assert "Tool: lexical_retrieval" in rendered
    assert "Latency: 12 ms" in rendered
    assert "No tool requested" not in rendered
