"""Internal structured protocol for tools and their observations."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

JSONValue = Any


class ToolStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"
    TIMEOUT = "timeout"


class ToolCall(BaseModel):
    """Provider-neutral request to run one registered tool."""

    model_config = ConfigDict(frozen=True)

    call_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, JSONValue] = Field(default_factory=dict)


class ToolResult(BaseModel):
    """Normalized, bounded observation returned by every tool."""

    model_config = ConfigDict(frozen=True)

    call_id: str
    tool_name: str
    status: ToolStatus
    output_summary: str
    data: dict[str, JSONValue] = Field(default_factory=dict)
    return_code: int | None = None
    duration_ms: int = Field(ge=0)

    @classmethod
    def denied(cls, call: ToolCall, reason: str) -> ToolResult:
        return cls(
            call_id=call.call_id,
            tool_name=call.name,
            status=ToolStatus.DENIED,
            output_summary=reason,
            duration_ms=0,
        )
