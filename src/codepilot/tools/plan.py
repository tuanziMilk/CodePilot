"""A small public planning tool for Phase 2 experiments."""

from __future__ import annotations

from pydantic import BaseModel, Field

from codepilot.models.protocol import ToolCall, ToolResult, ToolStatus
from codepilot.tools.base import Tool, ToolContext


class UpdatePlanInput(BaseModel):
    """A short, user-visible execution plan rather than private reasoning."""

    steps: list[str] = Field(min_length=1, max_length=6)


class UpdatePlanTool(Tool):
    name = "update_plan"
    description = (
        "Record a short public plan before repository actions. Arguments must look like "
        '{"steps":["Inspect files","Reproduce failure","Apply fix","Verify"]}; each item is '
        "a string, not an object. Call again only when the steps materially change; do not "
        "repeat an unchanged plan."
    )
    input_model = UpdatePlanInput

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        args = self.input_model.model_validate(call.arguments)
        steps = [step.strip() for step in args.steps]
        if any(not step or len(step) > 240 for step in steps):
            return ToolResult(
                call_id=call.call_id,
                tool_name=self.name,
                status=ToolStatus.ERROR,
                output_summary="Plan steps must be non-empty public summaries of at most 240 characters.",
                duration_ms=0,
            )
        return ToolResult(
            call_id=call.call_id,
            tool_name=self.name,
            status=ToolStatus.OK,
            output_summary="Recorded public plan:\n"
            + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, start=1)),
            data={"steps": steps},
            duration_ms=0,
        )
