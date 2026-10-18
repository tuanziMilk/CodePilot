"""Bounded public context for the ReAct-style action/observation loop.

The canonical RunState keeps the complete message history for auditability.  This
module creates a smaller provider view by replacing older completed steps with a
deterministic summary of observable tool calls and observations.  It never asks
for, parses, or stores private model reasoning.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from codepilot.models.messages import Message, MessageRole
from codepilot.trajectory.summaries import summarize_tool_calls


@dataclass(frozen=True)
class PublicRunSnapshot:
    """Small Harness-owned facts that remain useful after history compaction."""

    plan_steps: tuple[str, ...] = ()
    reproduction_failure_observed: bool = False
    repair_retry_count: int = 0


@dataclass(frozen=True)
class ContextView:
    """The messages sent to a provider plus observable compaction statistics."""

    messages: tuple[Message, ...]
    original_message_count: int
    selected_message_count: int
    original_chars: int
    selected_chars: int
    compacted_steps: int = 0

    @property
    def compacted(self) -> bool:
        return self.compacted_steps > 0


class ReActContextManager:
    """Keep pinned instructions and recent steps; summarize older public steps."""

    def __init__(
        self,
        *,
        mode: str = "compact",
        trigger_chars: int = 16_000,
        max_chars: int = 32_000,
        recent_steps: int = 4,
        summary_max_chars: int = 4_000,
    ) -> None:
        if mode not in {"full", "compact"}:
            raise ValueError("context mode must be full or compact.")
        if trigger_chars < 4_000:
            raise ValueError("context trigger_chars must be at least 4000.")
        if max_chars < 4_000:
            raise ValueError("context max_chars must be at least 4000.")
        if trigger_chars > max_chars:
            raise ValueError("context trigger_chars must not exceed max_chars.")
        if not 1 <= recent_steps <= 12:
            raise ValueError("context recent_steps must be between 1 and 12.")
        if summary_max_chars < 512:
            raise ValueError("context summary_max_chars must be at least 512.")
        self._mode = mode
        self._trigger_chars = trigger_chars
        self._max_chars = max_chars
        self._recent_steps = recent_steps
        self._summary_max_chars = summary_max_chars

    @property
    def mode(self) -> str:
        return self._mode

    def build(
        self,
        messages: list[Message],
        *,
        pinned_count: int,
        snapshot: PublicRunSnapshot,
    ) -> ContextView:
        """Build a provider view without mutating the complete canonical history."""

        original = tuple(messages)
        original_chars = _messages_chars(original)
        if self._mode == "full" or len(messages) <= pinned_count:
            return ContextView(
                messages=original,
                original_message_count=len(original),
                selected_message_count=len(original),
                original_chars=original_chars,
                selected_chars=original_chars,
            )

        prefix = tuple(messages[:pinned_count])
        steps = _split_steps(messages[pinned_count:])
        if not steps or original_chars < self._trigger_chars:
            return ContextView(
                messages=original,
                original_message_count=len(original),
                selected_message_count=len(original),
                original_chars=original_chars,
                selected_chars=original_chars,
            )

        keep_from = max(0, len(steps) - self._recent_steps)
        kept = steps[keep_from:]
        removed = steps[:keep_from]

        # Crossing the trigger starts one bounded compaction pass. recent_steps
        # controls the maximum recent window after that point; it is deliberately
        # not itself a trigger, so short runs retain exact source observations.
        if not removed and len(kept) > 1:
            removed.append(kept.pop(0))

        if not removed:
            # A single unusually large recent step is safer to keep intact than
            # to break its assistant tool_calls / tool observation relationship.
            return ContextView(
                messages=original,
                original_message_count=len(original),
                selected_message_count=len(original),
                original_chars=original_chars,
                selected_chars=original_chars,
            )

        selected = _compacted_messages(
            prefix,
            removed,
            kept,
            snapshot,
            self._summary_max_chars,
        )
        selected_chars = _messages_chars(selected)
        # Preserve at least the newest complete assistant/tool step so wire
        # tool-call pairs remain valid. Rebuild the public summary as older
        # complete steps are moved out of the recent window.
        while len(kept) > 1 and selected_chars > self._max_chars:
            removed.append(kept.pop(0))
            selected = _compacted_messages(
                prefix,
                removed,
                kept,
                snapshot,
                self._summary_max_chars,
            )
            selected_chars = _messages_chars(selected)
        if selected_chars >= original_chars:
            # Tiny steps (for example a short plan update) can be cheaper to
            # retain than the summary header needed to describe them.
            return ContextView(
                messages=original,
                original_message_count=len(original),
                selected_message_count=len(original),
                original_chars=original_chars,
                selected_chars=original_chars,
            )
        return ContextView(
            messages=selected,
            original_message_count=len(original),
            selected_message_count=len(selected),
            original_chars=original_chars,
            selected_chars=selected_chars,
            compacted_steps=len(removed),
        )


def _compacted_messages(
    prefix: tuple[Message, ...],
    removed: list[tuple[Message, ...]],
    kept: list[tuple[Message, ...]],
    snapshot: PublicRunSnapshot,
    summary_max_chars: int,
) -> tuple[Message, ...]:
    summary = Message(
        role=MessageRole.USER,
        content=_public_summary(removed, snapshot, summary_max_chars),
    )
    return prefix + (summary,) + _flatten(kept)


def _split_steps(messages: list[Message]) -> list[tuple[Message, ...]]:
    """Group one assistant action with its tool observations or verifier feedback."""

    steps: list[tuple[Message, ...]] = []
    current: list[Message] = []
    for message in messages:
        if message.role is MessageRole.ASSISTANT and current:
            steps.append(tuple(current))
            current = []
        current.append(message)
    if current:
        steps.append(tuple(current))
    return steps


def _flatten(steps: list[tuple[Message, ...]]) -> tuple[Message, ...]:
    return tuple(message for step in steps for message in step)


def _messages_chars(messages: tuple[Message, ...]) -> int:
    return sum(_message_chars(message) for message in messages)


def _message_chars(message: Message) -> int:
    tool_payload = [
        {"name": call.name, "arguments": call.arguments} for call in message.tool_calls
    ]
    return len(message.content) + len(json.dumps(tool_payload, ensure_ascii=False))


def _public_summary(
    steps: list[tuple[Message, ...]],
    snapshot: PublicRunSnapshot,
    limit: int,
) -> str:
    lines = [
        (
            "Earlier public action/observation summary. This is generated from observable tool "
            "calls and results, not private chain-of-thought."
        ),
        (
            "Current public state: "
            f"failed test reproduced={'yes' if snapshot.reproduction_failure_observed else 'no'}; "
            f"repair retries used={snapshot.repair_retry_count}; "
            f"plan={list(snapshot.plan_steps) if snapshot.plan_steps else 'none'}."
        ),
    ]
    for index, step in enumerate(steps, start=1):
        assistant = next(
            (message for message in step if message.role is MessageRole.ASSISTANT),
            None,
        )
        if assistant and assistant.tool_calls:
            action = summarize_tool_calls(assistant.tool_calls).text
            tools = ", ".join(_tool_label(call.name, call.arguments) for call in assistant.tool_calls)
            observations = [
                _one_line(message.content, 220)
                for message in step
                if message.role is MessageRole.TOOL
            ]
            observation = " | ".join(observations) or "no observation recorded"
            lines.append(f"- Earlier step {index}: {action} Tools: {tools}. Result: {observation}")
        elif assistant:
            feedback = next(
                (
                    _one_line(message.content, 300)
                    for message in step
                    if message.role is MessageRole.USER
                ),
                "no verifier feedback recorded",
            )
            lines.append(
                f"- Earlier step {index}: requested external verification. Feedback: {feedback}"
            )
        else:
            lines.append(f"- Earlier context: {_one_line(' '.join(m.content for m in step), 300)}")

    rendered = "\n".join(lines)
    if len(rendered) <= limit:
        return rendered
    marker = "\n... [older public context summary truncated by CodePilot]"
    return rendered[: max(0, limit - len(marker))] + marker


def _tool_label(name: str, arguments: dict[str, object]) -> str:
    target = arguments.get("path") or arguments.get("query") or arguments.get("command")
    return f"{name}({target})" if target else name


def _one_line(value: str, limit: int) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else compact[:limit] + " ... [truncated]"
