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
            event_type="context_compaction",
            context_messages_before=12,
            context_messages_after=8,
            context_chars_before=40_000,
            context_chars_after=20_000,
            context_steps_compacted=3,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=1,
            event_type="assistant_response",
            latency_ms=5,
            context_mode="compact",
            context_compacted=True,
            context_messages_before=12,
            context_messages_after=8,
            context_chars_before=40_000,
            context_chars_after=20_000,
            context_steps_compacted=3,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=1,
            event_type="tool_result",
            tool_name="read_file",
            state_change="tool_error",
            latency_ms=7,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=2,
            event_type="tool_result",
            tool_name="update_plan",
            state_change="tool_denied",
            latency_ms=0,
        )
    )
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=2,
            event_type="tool_result",
            tool_name="update_plan",
            state_change="tool_plan_unchanged",
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
    assert metrics["tool_call_count"] == 3
    assert metrics["read_file_count"] == 1
    assert metrics["update_plan_count"] == 2
    assert metrics["plan_noop_count"] == 1
    assert metrics["context_compaction_count"] == 1
    assert metrics["max_context_chars_before"] == 40_000
    assert metrics["max_context_chars_after"] == 20_000
    assert metrics["max_context_messages_sent"] == 8
    assert metrics["max_context_steps_compacted"] == 3
    assert metrics["context_request_count"] == 1
    assert metrics["total_context_chars_sent"] == 20_000
    assert metrics["context_chars_saved"] == 20_000
    assert metrics["run_elapsed_ms"] >= 0


def test_writer_measures_uncompacted_provider_context(tmp_path: Path) -> None:
    writer = TrajectoryWriter(tmp_path / "full-run", _metadata())
    writer.write_event(
        TrajectoryEvent(
            run_id="metrics-run",
            step=1,
            event_type="assistant_response",
            context_mode="full",
            context_compacted=False,
            context_messages_before=7,
            context_messages_after=7,
            context_chars_before=9_500,
            context_chars_after=9_500,
        )
    )

    metrics = writer.metrics()

    assert metrics["context_request_count"] == 1
    assert metrics["total_context_chars_sent"] == 9_500
    assert metrics["max_context_chars_before"] == 9_500
    assert metrics["max_context_chars_after"] == 9_500
    assert metrics["context_chars_saved"] == 0
