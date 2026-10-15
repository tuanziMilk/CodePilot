"""Public, deterministic action summaries derived from structured tool calls.

This module intentionally does not inspect model reasoning or request a rationale
from the provider. It translates the observable action selected by the model into
short human-readable labels for trajectory inspection.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from codepilot.models.protocol import ToolCall


@dataclass(frozen=True)
class ActionSummary:
    """A public account of a requested operation, not chain-of-thought."""

    action: str
    reason: str
    targets: tuple[str, ...]

    @property
    def text(self) -> str:
        labels = {
            "inspect_repository": "Inspect repository files.",
            "inspect_files": "Inspect relevant source and test files.",
            "search_code": "Search relevant code.",
            "apply_minimal_edit": "Apply a minimal source edit.",
            "run_command": "Run an allow-listed command.",
            "verify_task": "Run the declared verification command.",
            "update_plan": "Record a public execution plan.",
            "execute_tools": "Execute bounded repository operations.",
        }
        return labels[self.action]


def summarize_tool_calls(calls: tuple[ToolCall, ...]) -> ActionSummary:
    """Describe what the model requested using only tool names and arguments."""

    names = {call.name for call in calls}
    targets = tuple(target for call in calls for target in _targets_for(call))

    if names == {"list_files"}:
        return ActionSummary(
            action="inspect_repository",
            reason="Discover the repository layout before selecting relevant files.",
            targets=targets or (".",),
        )
    if names == {"read_file"}:
        return ActionSummary(
            action="inspect_files",
            reason="Inspect source or test contents to understand the current behavior.",
            targets=targets,
        )
    if names == {"search_text"}:
        return ActionSummary(
            action="search_code",
            reason="Locate code related to the task before making a change.",
            targets=targets,
        )
    if names == {"edit_file"}:
        return ActionSummary(
            action="apply_minimal_edit",
            reason="Apply one bounded exact replacement to the selected source file.",
            targets=targets,
        )
    if names == {"bash"}:
        return ActionSummary(
            action="run_command",
            reason="Inspect or verify repository behavior with an allow-listed command.",
            targets=targets,
        )
    if names == {"update_plan"}:
        return ActionSummary(
            action="update_plan",
            reason="Record a short public plan before repository actions.",
            targets=(),
        )
    return ActionSummary(
        action="execute_tools",
        reason="Perform the requested bounded repository operations.",
        targets=targets,
    )


def verification_summary(command: str) -> ActionSummary:
    """Describe Harness-owned verification rather than model reasoning."""

    return ActionSummary(
        action="verify_task",
        reason="The Agent stopped requesting tools, so run the declared verifier.",
        targets=(command,),
    )


def _targets_for(call: ToolCall) -> tuple[str, ...]:
    arguments: dict[str, Any] = call.arguments
    if call.name in {"list_files", "read_file", "edit_file"}:
        path = arguments.get("path")
        return (str(path),) if path else ()
    if call.name == "search_text":
        path = str(arguments.get("path", "."))
        query = arguments.get("query")
        return (f"{path} (query: {query})",) if query else (path,)
    if call.name == "bash":
        command = arguments.get("command")
        return (str(command),) if command else ()
    return ()
