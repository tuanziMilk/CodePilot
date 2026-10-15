"""The constrained shell tool."""

from __future__ import annotations

from pydantic import BaseModel, Field

from codepilot.models.protocol import ToolCall, ToolResult, ToolStatus
from codepilot.permissions.policy import PermissionDenied
from codepilot.tools.base import Tool, ToolContext


class BashInput(BaseModel):
    command: str = Field(min_length=1, max_length=500)


class BashTool(Tool):
    name = "bash"
    description = (
        "Run allow-listed local inspection, selected git status/diff checks, pytest, "
        "or offline Maven test commands in Git Bash. Shell composition is not allowed."
    )
    input_model = BashInput

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        try:
            args = self.input_model.model_validate(call.arguments)
            context.permissions.authorize_command(args.command)
        except (PermissionDenied, ValueError) as error:
            return ToolResult.denied(call, str(error))

        process = context.environment.run(args.command, context.command_timeout_seconds)
        status = ToolStatus.TIMEOUT if process.timed_out else ToolStatus.OK
        output = process.stdout
        if process.stderr:
            output = f"{output}\n[stderr]\n{process.stderr}".strip()
        if process.timed_out:
            output = f"Command timed out.\n{output}".strip()
        output = (
            f"Status: {status.value}\nReturn code: {process.return_code}\n"
            f"{output or '(command produced no output)'}"
        )
        return ToolResult(
            call_id=call.call_id,
            tool_name=self.name,
            status=status,
            output_summary=output,
            data={"command": args.command},
            return_code=process.return_code,
            duration_ms=process.duration_ms,
        )
