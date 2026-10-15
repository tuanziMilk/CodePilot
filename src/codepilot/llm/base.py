"""Stable LLM boundary used by the Agent Harness."""

from __future__ import annotations

from abc import ABC, abstractmethod

from codepilot.models.messages import ChatRequest, ChatResponse


class ProviderError(RuntimeError):
    """Base error from an LLM provider adapter."""


class ProviderProtocolError(ProviderError):
    """The provider returned a response that cannot be normalized safely."""


class LLMProvider(ABC):
    """A synchronous completion boundary; concrete providers own transport quirks."""

    @abstractmethod
    def complete(self, request: ChatRequest) -> ChatResponse:
        """Return one normalized model response or raise a typed ProviderError."""

