"""Messages exchanged between the Harness and a provider adapter."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from codepilot.models.protocol import ToolCall, ToolResult


class MessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class Message(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: MessageRole
    content: str = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


class ToolDefinition(BaseModel):
    """One provider-neutral JSON-schema tool definition."""

    model_config = ConfigDict(frozen=True)

    name: str
    description: str
    parameters: dict[str, Any]


class ChatRequest(BaseModel):
    model_config = ConfigDict(frozen=True)

    messages: tuple[Message, ...]
    tools: tuple[ToolDefinition, ...]
    temperature: float
    max_output_tokens: int


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cost: float | None = None


class ChatResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    message: Message
    usage: Usage = Field(default_factory=Usage)
    latency_ms: int = Field(ge=0)
    provider_request_id: str | None = None
    request_retry_count: int = Field(default=0, ge=0)


def tool_observation(result: ToolResult) -> Message:
    """Convert a normalized tool result into an explicit public observation."""

    header = [f"Tool: {result.tool_name}", f"Status: {result.status.value}"]
    if result.return_code is not None:
        header.append(f"Return code: {result.return_code}")
    header.append("Observation:")

    return Message(
        role=MessageRole.TOOL,
        content="\n".join(header + [result.output_summary]),
        tool_call_id=result.call_id,
    )

