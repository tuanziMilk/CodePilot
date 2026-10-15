"""DeepSeek OpenAI-compatible adapter.

Only this module knows the OpenAI-compatible wire representation. Every caller
above it uses CodePilot message and tool protocol models.
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

import httpx

from codepilot.config.settings import Settings
from codepilot.llm.base import LLMProvider, ProviderError, ProviderProtocolError
from codepilot.models.messages import (
    ChatRequest,
    ChatResponse,
    Message,
    MessageRole,
    Usage,
)
from codepilot.models.protocol import ToolCall


class OpenAICompatibleProvider(LLMProvider):
    """Translate the internal protocol for an explicitly configured compatible endpoint."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def complete(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": self._settings.llm_model,
            "messages": [self._to_wire_message(message) for message in request.messages],
            "tools": [self._to_wire_tool(tool) for tool in request.tools],
            "temperature": request.temperature,
            "max_tokens": request.max_output_tokens,
        }
        endpoint = f"{self._settings.llm_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._settings.llm_api_key.get_secret_value()}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        request_started = time.perf_counter()
        for attempt in range(self._settings.llm_request_retries + 1):
            try:
                with httpx.Client(timeout=self._settings.llm_timeout_seconds) as client:
                    response = client.post(endpoint, headers=headers, json=payload)
                response.raise_for_status()
                latency_ms = round((time.perf_counter() - request_started) * 1000)
                normalized = self._from_wire_response(response.json(), latency_ms)
                return normalized.model_copy(update={"request_retry_count": attempt})
            except httpx.HTTPStatusError as error:
                last_error = error
                if error.response.status_code not in {408, 409, 429} and error.response.status_code < 500:
                    break
            except httpx.RequestError as error:
                last_error = error
            except (KeyError, IndexError, TypeError, ValueError) as error:
                raise ProviderProtocolError("Provider response did not match the tool-calling protocol.") from error

            if attempt < self._settings.llm_request_retries:
                time.sleep(min(2**attempt, 4))

        # Do not persist request/response objects: they may contain credentials,
        # provider diagnostics or complete source prompts.
        detail = (
            f"HTTP {last_error.response.status_code}"
            if isinstance(last_error, httpx.HTTPStatusError)
            else type(last_error).__name__
        )
        raise ProviderError(f"Provider request failed ({detail}); attempts={attempt + 1}.") from last_error

    @staticmethod
    def _to_wire_tool(tool: Any) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _to_wire_message(message: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": message.role.value, "content": message.content}
        if message.role is MessageRole.ASSISTANT and message.tool_calls:
            wire["tool_calls"] = [
                {
                    "id": call.call_id,
                    "type": "function",
                    "function": {
                        "name": call.name,
                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                    },
                }
                for call in message.tool_calls
            ]
        if message.role is MessageRole.TOOL:
            if not message.tool_call_id:
                raise ProviderProtocolError("Tool observations must reference a tool_call_id.")
            wire["tool_call_id"] = message.tool_call_id
        return wire

    @staticmethod
    def _from_wire_response(payload: dict[str, Any], latency_ms: int) -> ChatResponse:
        if not isinstance(payload, dict):
            raise ProviderProtocolError("Provider payload must be an object.")
        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderProtocolError("Provider choices must contain a message.")
        choice_message = choices[0].get("message")
        if not isinstance(choice_message, dict):
            raise ProviderProtocolError("Provider message must be an object.")
        wire_calls = choice_message.get("tool_calls")
        wire_calls = [] if wire_calls is None else wire_calls
        if not isinstance(wire_calls, list):
            raise ProviderProtocolError("Provider tool_calls must be a list.")
        content = choice_message.get("content")
        content = "" if content is None else content
        if not isinstance(content, str):
            raise ProviderProtocolError("Provider visible content must be text.")
        calls: list[ToolCall] = []
        for wire_call in wire_calls:
            if not isinstance(wire_call, dict) or not isinstance(wire_call.get("function"), dict):
                raise ProviderProtocolError("Each tool call must contain a function object.")
            function = wire_call["function"]
            name = function.get("name")
            raw_arguments = function.get("arguments", "{}")
            if not isinstance(name, str) or not name:
                raise ProviderProtocolError("Tool call did not contain a valid function name.")
            if not isinstance(raw_arguments, str):
                raise ProviderProtocolError("Tool arguments must be encoded as a JSON string.")
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError as error:
                raise ProviderProtocolError(f"Tool arguments were not valid JSON for {name}.") from error
            if not isinstance(arguments, dict):
                raise ProviderProtocolError(f"Tool arguments must be an object for {name}.")
            call_id = wire_call.get("id") or f"codepilot-{uuid.uuid4().hex}"
            if not isinstance(call_id, str):
                raise ProviderProtocolError("Tool call id must be text.")
            calls.append(
                ToolCall(
                    call_id=call_id,
                    name=name,
                    arguments=arguments,
                )
            )

        usage_payload = payload.get("usage")
        usage_payload = {} if usage_payload is None else usage_payload
        if not isinstance(usage_payload, dict):
            raise ProviderProtocolError("Provider usage must be an object.")
        usage = Usage(
            input_tokens=usage_payload.get("prompt_tokens"),
            output_tokens=usage_payload.get("completion_tokens"),
            total_tokens=usage_payload.get("total_tokens"),
            cost=None,
        )
        return ChatResponse(
            message=Message(
                role=MessageRole.ASSISTANT,
                content=content,
                tool_calls=tuple(calls),
            ),
            usage=usage,
            latency_ms=latency_ms,
            provider_request_id=payload.get("id"),
        )


class DeepSeekOpenAICompatibleProvider(OpenAICompatibleProvider):
    """Backward-compatible DeepSeek adapter name used by the learning material."""

    def __init__(self, settings: Settings) -> None:
        if settings.llm_provider != "deepseek":
            raise ValueError("DeepSeek adapter requires LLM_PROVIDER=deepseek.")
        super().__init__(settings)

