"""Tool interface and execution context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from pydantic import BaseModel

from codepilot.environment.git_bash import GitBashEnvironment
from codepilot.environment.workspace import Workspace
from codepilot.models.messages import ToolDefinition
from codepilot.models.protocol import ToolCall, ToolResult
from codepilot.permissions.policy import PermissionPolicy


@dataclass(frozen=True)
class ToolContext:
    workspace: Workspace
    environment: GitBashEnvironment
    permissions: PermissionPolicy
    command_timeout_seconds: float


class Tool(ABC):
    """One bounded operation exposed as a provider-neutral JSON-schema tool."""

    name: str
    description: str
    input_model: type[BaseModel]

    def definition(self) -> ToolDefinition:
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=self.input_model.model_json_schema(),
        )

    @abstractmethod
    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        """Validate and perform exactly one operation."""
