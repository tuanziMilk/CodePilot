"""Tool registry and centralized execution boundary."""

from __future__ import annotations

from collections.abc import Iterable
from time import perf_counter

from codepilot.models.messages import ToolDefinition
from codepilot.models.protocol import ToolCall, ToolResult, ToolStatus
from codepilot.tools.base import Tool, ToolContext


class ToolDispatcher:
    def __init__(self, tools: Iterable[Tool], context: ToolContext) -> None:
        tool_list = tuple(tools)
        self._tools = {tool.name: tool for tool in tool_list}
        if len(self._tools) != len(tool_list):
            raise ValueError("Tool names must be unique.")
        self._context = context

    def definitions(self) -> tuple[ToolDefinition, ...]:
        return tuple(tool.definition() for tool in self._tools.values())

    def execute(self, call: ToolCall) -> ToolResult:
        started = perf_counter()
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolStatus.ERROR,
                output_summary=f"Unknown tool: {call.name}",
                duration_ms=round((perf_counter() - started) * 1000),
            )
        try:
            return tool.execute(call, self._context)
        except Exception as error:  # noqa: BLE001 - tool faults must become observations.
            return ToolResult(
                call_id=call.call_id,
                tool_name=call.name,
                status=ToolStatus.ERROR,
                output_summary=f"Tool execution failed: {type(error).__name__}: {error}",
                duration_ms=round((perf_counter() - started) * 1000),
            )
