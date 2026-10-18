"""A dependency-free terminal viewer for machine-readable trajectory JSONL files."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


def render_trajectory(path: Path) -> str:
    """Render new and historical trajectory files without changing their schema."""

    events = _read_events(path)
    by_step: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        by_step[int(event["step"])].append(event)

    sections: list[str] = []
    for step in sorted(by_step):
        step_events = by_step[step]
        retrieval = next(
            (event for event in step_events if event.get("event_type") == "retrieval"),
            None,
        )
        if retrieval:
            sections.append(_render_retrieval(step, retrieval))
            step_events = [event for event in step_events if event is not retrieval]
            if not step_events:
                continue
        verification = next(
            (event for event in step_events if event.get("event_type") == "verification"),
            None,
        )
        if verification:
            context = next(
                (
                    event
                    for event in step_events
                    if event.get("event_type") == "context_compaction"
                ),
                None,
            )
            if context is None:
                context = next(
                    (
                        event
                        for event in step_events
                        if event.get("event_type") == "assistant_response"
                        and event.get("context_chars_after") is not None
                    ),
                    None,
                )
            sections.append(_render_verification(verification, context))
            continue
        sections.append(_render_step(step, step_events))
    return "\n\n".join(section for section in sections if section)


def _read_events(path: Path) -> list[dict[str, Any]]:
    """Accept standard JSONL and historical pretty-printed object streams."""

    events: list[dict[str, Any]] = []
    content = path.read_text(encoding="utf-8")
    decoder = json.JSONDecoder()
    offset = 0
    while offset < len(content):
        while offset < len(content) and content[offset].isspace():
            offset += 1
        if offset >= len(content):
            break
        try:
            event, offset = decoder.raw_decode(content, offset)
        except json.JSONDecodeError as error:
            line_number = content.count("\n", 0, error.pos) + 1
            raise ValueError(f"Invalid JSON near line {line_number}: {error}") from error
        if not isinstance(event, dict) or "step" not in event:
            line_number = content.count("\n", 0, offset) + 1
            raise ValueError(f"Event ending near line {line_number} is missing its step.")
        events.append(event)
    return events


def _render_step(step: int, events: list[dict[str, Any]]) -> str:
    assistant = next(
        (event for event in events if event.get("event_type") == "assistant_response"),
        {},
    )
    tool_events = [event for event in events if event.get("event_type") == "tool_result"]
    action = assistant.get("action_summary") or _legacy_action(tool_events)
    lines = [f"Step {step}", f"Action: {action}"]
    context = next(
        (event for event in events if event.get("event_type") == "context_compaction"),
        None,
    )
    if context:
        lines.append(_context_line(context))
    elif assistant.get("context_chars_after") is not None:
        lines.append(_request_context_line(assistant))
    usage = assistant.get("token_usage") or {}
    if usage:
        lines.append(f"Tokens: input={usage.get('input_tokens')} output={usage.get('output_tokens')} total={usage.get('total_tokens')}")
    if assistant.get("latency_ms") is not None:
        lines.append(f"LLM latency: {assistant['latency_ms']} ms")
    if assistant.get("reason"):
        lines.append(f"Why: {assistant['reason']}")
    if assistant.get("targets"):
        lines.append(f"Targets: {', '.join(assistant['targets'])}")
    for event in tool_events:
        tool = event.get("tool_name", "unknown")
        arguments = _format_arguments(event.get("tool_arguments"))
        lines.append(f"Tool: {tool}{arguments}")
        lines.append(f"Result: {_compact(event.get('tool_result_summary'))}")
        lines.append(f"Status: {_status(event)}")
        if event.get("return_code") is not None:
            lines.append(f"Return code: {event['return_code']}")
        if event.get("latency_ms") is not None:
            lines.append(f"Tool latency: {event['latency_ms']} ms")
    for event in events:
        if event.get("event_type") in {"termination", "provider_error"}:
            lines.append(f"Terminal state: {event.get('state_change')}")
            if event.get("tool_result_summary"):
                lines.append(f"Detail: {_compact(event['tool_result_summary'])}")
    return "\n".join(lines)


def _render_retrieval(step: int, event: dict[str, Any]) -> str:
    lines = [f"Step {step}", f"Action: {event.get('action_summary') or 'Retrieve repository context.'}"]
    if event.get("reason"):
        lines.append(f"Why: {event['reason']}")
    if event.get("targets"):
        lines.append(f"Targets: {', '.join(event['targets'])}")
    lines.append(f"Tool: {event.get('tool_name', 'retrieval')}")
    if event.get("tool_result_summary"):
        lines.append(f"Result: {_compact(event['tool_result_summary'])}")
    if event.get("latency_ms") is not None:
        lines.append(f"Latency: {event['latency_ms']} ms")
    lines.append(f"Status: {event.get('state_change', 'unknown')}")
    return "\n".join(lines)


def _render_verification(
    event: dict[str, Any], context: dict[str, Any] | None = None
) -> str:
    lines = ["Verification"]
    if context:
        lines.append(
            _context_line(context)
            if context.get("event_type") == "context_compaction"
            else _request_context_line(context)
        )
    if event.get("tool_result_summary"):
        lines.append(f"Result: {_compact(event['tool_result_summary'])}")
    lines.append(f"Status: {event.get('state_change', 'unknown')}")
    lines.append(f"Return code: {event.get('return_code')}")
    if event.get("latency_ms") is not None:
        lines.append(f"Latency: {event['latency_ms']} ms")
    return "\n".join(lines)


def _context_line(event: dict[str, Any]) -> str:
    return (
        "Context: compacted "
        f"{event.get('context_steps_compacted', 0)} older step(s); "
        f"messages {event.get('context_messages_before')}→"
        f"{event.get('context_messages_after')}; "
        f"chars {event.get('context_chars_before')}→{event.get('context_chars_after')}"
    )


def _request_context_line(event: dict[str, Any]) -> str:
    mode = event.get("context_mode", "unknown")
    compacted = "compacted" if event.get("context_compacted") else "unchanged"
    return (
        f"Context: {mode}, {compacted}; "
        f"messages sent={event.get('context_messages_after')}; "
        f"chars sent={event.get('context_chars_after')}"
    )


def _legacy_action(tool_events: list[dict[str, Any]]) -> str:
    if not tool_events:
        return "No tool requested; prepare explicit verification."
    tools = ", ".join(str(event.get("tool_name", "unknown")) for event in tool_events)
    return f"Legacy trajectory: infer intent from tool(s): {tools}."


def _format_arguments(arguments: Any) -> str:
    if not arguments:
        return ""
    rendered = ", ".join(f"{key}={value!r}" for key, value in arguments.items())
    return f" ({rendered})"


def _compact(value: Any, limit: int = 300) -> str:
    text = " ".join(str(value or "(no output)").split())
    return text if len(text) <= limit else text[:limit] + " ... [truncated]"


def _status(event: dict[str, Any]) -> str:
    state = str(event.get("state_change", "unknown"))
    return state.removeprefix("tool_").upper()


def main() -> int:
    parser = argparse.ArgumentParser(description="Render a CodePilot trajectory JSONL file.")
    parser.add_argument("trajectory", type=Path)
    args = parser.parse_args()
    print(render_trajectory(args.trajectory))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
