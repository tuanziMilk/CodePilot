"""JSONL trajectory output with deliberately bounded, non-secret fields."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RunMetadata(BaseModel):
    """Redacted metadata sufficient to reproduce a run configuration."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    task_id: str | None = None
    provider: str
    model: str
    base_url_identifier: str
    temperature: float
    max_output_tokens: int
    llm_request_retries: int
    agent_max_steps: int
    agent_max_retries: int
    tool_policy_version: str
    prompt_version: str
    planning_enabled: bool = False
    planning_mode: str = "optional"
    requires_reproduction: bool = False
    retrieval_mode: str = "none"
    retrieval_top_k: int = 0
    context_mode: str = "compact"
    agent_context_trigger_chars: int = 16_000
    agent_context_max_chars: int = 32_000
    agent_context_recent_steps: int = 4
    command_timeout_seconds: float = 60
    git_commit: str | None = None
    start_time: datetime


class TrajectoryEvent(BaseModel):
    """One action-oriented event, never a private-reasoning record."""

    model_config = ConfigDict(frozen=True)

    run_id: str
    step: int
    event_type: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    action_summary: str | None = None
    action: str | None = None
    reason: str | None = None
    targets: list[str] | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    tool_result_summary: str | None = None
    return_code: int | None = None
    state_change: str | None = None
    verification_result: bool | None = None
    retry_count: int | None = None
    plan_version: int | None = None
    plan_steps: list[str] | None = None
    token_usage: dict[str, int | float | None] | None = None
    provider_retry_count: int | None = None
    latency_ms: int | None = None
    context_mode: str | None = None
    context_compacted: bool | None = None
    context_messages_before: int | None = None
    context_messages_after: int | None = None
    context_chars_before: int | None = None
    context_chars_after: int | None = None
    context_steps_compacted: int | None = None


class TrajectoryWriter:
    """Append events and preserve immutable initial metadata for one run."""

    def __init__(self, artifact_dir: Path, metadata: RunMetadata) -> None:
        self.artifact_dir = artifact_dir
        self.run_id = metadata.run_id
        self._start_time = metadata.start_time
        self._events: list[TrajectoryEvent] = []
        self.artifact_dir.mkdir(parents=True, exist_ok=True)
        self._events_path = self.artifact_dir / "trajectory.jsonl"
        self._metadata_path = self.artifact_dir / "run_metadata.json"
        self._metadata_path.write_text(
            metadata.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def write_event(self, event: TrajectoryEvent) -> None:
        with self._events_path.open("a", encoding="utf-8") as stream:
            stream.write(event.model_dump_json() + "\n")
        self._events.append(event)

    def metrics(self) -> dict[str, int]:
        """Return small aggregate metrics without changing the JSONL schema."""

        def latency(event_type: str) -> int:
            return sum(
                event.latency_ms or 0
                for event in self._events
                if event.event_type == event_type
            )

        event_latency_ms = sum(event.latency_ms or 0 for event in self._events)
        elapsed_ms = max(0, round((datetime.now(UTC) - self._start_time).total_seconds() * 1000))
        tool_events = [event for event in self._events if event.event_type == "tool_result"]
        context_request_events = [
            event
            for event in self._events
            if event.event_type in {"assistant_response", "provider_error"}
            and event.context_chars_after is not None
        ]
        metrics = {
            "llm_latency_ms": latency("assistant_response"),
            "retrieval_latency_ms": latency("retrieval"),
            "tool_latency_ms": latency("tool_result"),
            "verification_latency_ms": latency("verification"),
            "observed_event_latency_ms": event_latency_ms,
            "run_elapsed_ms": elapsed_ms,
            "tool_error_count": sum(
                event.event_type == "tool_result" and event.state_change == "tool_error"
                for event in self._events
            ),
            "tool_denied_count": sum(
                event.event_type == "tool_result" and event.state_change == "tool_denied"
                for event in self._events
            ),
            "tool_call_count": len(tool_events),
            "plan_noop_count": sum(
                event.state_change == "tool_plan_unchanged" for event in tool_events
            ),
            "provider_request_retry_count": sum(
                event.provider_retry_count or 0 for event in self._events
            ),
            "context_compaction_count": sum(
                event.event_type == "context_compaction" for event in self._events
            ),
            "max_context_chars_before": max(
                (event.context_chars_before or 0 for event in context_request_events), default=0
            ),
            "max_context_chars_after": max(
                (event.context_chars_after or 0 for event in context_request_events), default=0
            ),
            "max_context_messages_sent": max(
                (event.context_messages_after or 0 for event in context_request_events), default=0
            ),
            "max_context_steps_compacted": max(
                (event.context_steps_compacted or 0 for event in self._events), default=0
            ),
            "context_request_count": len(context_request_events),
            "total_context_chars_sent": sum(
                event.context_chars_after or 0 for event in context_request_events
            ),
            "context_chars_saved": sum(
                max(0, (event.context_chars_before or 0) - (event.context_chars_after or 0))
                for event in context_request_events
            ),
        }
        for tool_name in (
            "list_files",
            "read_file",
            "search_text",
            "edit_file",
            "bash",
            "update_plan",
        ):
            metrics[f"{tool_name}_count"] = sum(
                event.tool_name == tool_name for event in tool_events
            )
        return metrics

    def write_final_summary(self, summary: dict[str, Any]) -> None:
        safe_path = self.artifact_dir / "final_summary.json"
        safe_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
