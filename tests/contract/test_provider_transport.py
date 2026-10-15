import httpx
import pytest

from codepilot.config.settings import Settings
from codepilot.llm.base import ProviderError, ProviderProtocolError
from codepilot.llm.deepseek import OpenAICompatibleProvider
from codepilot.models.messages import ChatRequest


def _settings() -> Settings:
    return Settings(
        llm_provider="compatible",
        llm_model="mock-model",
        llm_base_url="https://provider.example/v1",
        llm_api_key="must-not-appear",
        llm_request_retries=1,
    )


def test_retry_is_provider_local_and_does_not_persist_reasoning(monkeypatch) -> None:
    attempts = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(request)
        if len(attempts) == 1:
            return httpx.Response(503)
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "Ready.", "reasoning_content": "private"}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 5, "total_tokens": 25},
        })

    actual_client = httpx.Client
    monkeypatch.setattr("codepilot.llm.deepseek.httpx.Client", lambda **kwargs: actual_client(
        transport=httpx.MockTransport(handler), **kwargs,
    ))
    monkeypatch.setattr("codepilot.llm.deepseek.time.sleep", lambda seconds: None)
    result = OpenAICompatibleProvider(_settings()).complete(
        ChatRequest(messages=(), tools=(), temperature=0, max_output_tokens=30)
    )
    assert len(attempts) == 2
    assert result.request_retry_count == 1
    assert result.usage.total_tokens == 25
    assert "private" not in result.model_dump_json()


def test_provider_failure_never_logs_response_body_or_credential(monkeypatch) -> None:
    actual_client = httpx.Client
    monkeypatch.setattr("codepilot.llm.deepseek.httpx.Client", lambda **kwargs: actual_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(
            401, text="must-not-appear source diagnostics",
        )), **kwargs,
    ))
    with pytest.raises(ProviderError) as error:
        OpenAICompatibleProvider(_settings()).complete(
            ChatRequest(messages=(), tools=(), temperature=0, max_output_tokens=30)
        )
    assert "HTTP 401" in str(error.value)
    assert "must-not-appear" not in str(error.value)
    assert "attempts=1" in str(error.value)


@pytest.mark.parametrize("message", [
    42,
    {"tool_calls": [42]},
    {"tool_calls": {"function": {}}},
    {"tool_calls": [{"function": "not-an-object"}]},
    {"tool_calls": [{"function": {"name": "read_file", "arguments": {"path": "x"}}}]},
    {"tool_calls": [{"id": 42, "function": {"name": "read_file", "arguments": "{}"}}]},
    {"content": ["wrong-shape"]},
])
def test_malformed_wire_structure_is_a_provider_error(message) -> None:
    with pytest.raises(ProviderProtocolError):
        OpenAICompatibleProvider._from_wire_response({"choices": [{"message": message}]}, 0)
