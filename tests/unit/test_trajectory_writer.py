from datetime import UTC, datetime
from pathlib import Path

from codepilot.trajectory.writer import RunMetadata, TrajectoryEvent, TrajectoryWriter


def _metadata() -> RunMetadata:
    return RunMetadata(
        run_id="metrics-run",
        provider="test",
        model="test-model",
        base_url_identifier="test",
        temperature=0,
        max_output_tokens=10,
        llm_request_retries=0,
        agent_max_steps=2,
        agent_max_retries=0,
        tool_policy_version="test",
        prompt_version="test",
        start_time=datetime.now(UTC),
    )


def test_writer_aggregates_observable_latency_and_tool_statuses(tmp_path: Path) -> None:
    writer = TrajectoryWriter(tmp_path / "run", _metadata())
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=0,
            event_type="retrieval",
            latency_ms=3,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=1,
            event_type="assistant_response",
            latency_ms=5,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=1,
            event_type="tool_result",
            state_change="tool_error",
            latency_ms=7,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=2,
            event_type="tool_result",
            state_change="tool_denied",
            latency_ms=0,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=2,
            event_type="verification",
            latency_ms=11,
        )
    )

    metrics = writer.metrics()

    assert metrics["llm_latency_ms"] == 5
    assert metrics["retrieval_latency_ms"] == 3
    assert metrics["tool_latency_ms"] == 7
    assert metrics["verification_latency_ms"] == 11
    assert metrics["observed_event_latency_ms"] == 26
    assert metrics["tool_error_count"] == 1
    assert metrics["tool_denied_count"] == 1
    assert metrics["run_elapsed_ms"] >= 0
