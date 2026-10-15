import pytest

from codepilot.llm.base import ProviderProtocolError
from codepilot.llm.deepseek import DeepSeekOpenAICompatibleProvider


def test_wire_response_becomes_internal_tool_call() -> None:
    response = DeepSeekOpenAICompatibleProvider._from_wire_response(
        {
            "id": "request-1",
            "choices": [
                {
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-1",
                                "function": {
                                    "name": "read_file",
                                    "arguments": "{\"path\": \"calculator.py\"}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 4, "total_tokens": 14},
        },
        latency_ms=12,
    )

    assert response.message.tool_calls[0].name == "read_file"
    assert response.message.tool_calls[0].arguments == {"path": "calculator.py"}
    assert response.usage.total_tokens == 14


def test_malformed_tool_arguments_fail_at_provider_boundary() -> None:
    with pytest.raises(ProviderProtocolError):
        DeepSeekOpenAICompatibleProvider._from_wire_response(
            {
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "function": {
                                        "name": "read_file",
                                        "arguments": "not-json",
                                    }
                                }
                            ]
                        }
                    }
                ]
            },
            latency_ms=1,
        )

