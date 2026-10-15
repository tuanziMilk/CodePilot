"""Safe workspace-bound file inspection and exact-replacement editing tools."""

from __future__ import annotations

import time

from pydantic import BaseModel, Field

from codepilot.environment.workspace import WorkspaceViolation
from codepilot.models.protocol import ToolCall, ToolResult, ToolStatus
from codepilot.tools.base import Tool, ToolContext


def _elapsed_ms(start: float) -> int:
    return round((time.perf_counter() - start) * 1000)


def _error(call: ToolCall, message: str, start: float) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status=ToolStatus.ERROR,
        output_summary=message,
        duration_ms=_elapsed_ms(start),
    )


def _denied(call: ToolCall, message: str, start: float) -> ToolResult:
    return ToolResult(
        call_id=call.call_id,
        tool_name=call.name,
        status=ToolStatus.DENIED,
        output_summary=message,
        duration_ms=_elapsed_ms(start),
    )


class ListFilesInput(BaseModel):
    path: str = "."
    max_entries: int = Field(default=100, ge=1, le=500)


class ListFilesTool(Tool):
    name = "list_files"
    description = "List files below a workspace-relative directory, excluding protected paths."
    input_model = ListFilesInput

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        start = time.perf_counter()
        try:
            args = self.input_model.model_validate(call.arguments)
            root = context.workspace.resolve(args.path)
            if not root.is_dir():
                return _error(call, f"Not a directory: {args.path}", start)
            files: list[str] = []
            for path in root.rglob("*"):
                if len(files) >= args.max_entries:
                    break
                if not path.is_file():
                    continue
                try:
                    relative = context.workspace.display_path(path)
                    context.workspace.resolve(relative)
                    files.append(relative)
                except WorkspaceViolation:
                    continue
            files.sort()
            return ToolResult(
                call_id=call.call_id,
                tool_name=self.name,
                status=ToolStatus.OK,
                output_summary="\n".join(files) or "(no readable files)",
                data={"files": files, "truncated": len(files) >= args.max_entries},
                duration_ms=_elapsed_ms(start),
            )
        except WorkspaceViolation as error:
            return _denied(call, str(error), start)
        except ValueError as error:
            return _error(call, str(error), start)


class ReadFileInput(BaseModel):
    path: str
    max_chars: int = Field(default=8_000, ge=1, le=40_000)


class ReadFileTool(Tool):
    name = "read_file"
    description = "Read a UTF-8 text file inside the workspace with a size limit."
    input_model = ReadFileInput

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        start = time.perf_counter()
        try:
            args = self.input_model.model_validate(call.arguments)
            path = context.workspace.resolve(args.path)
            content = path.read_text(encoding="utf-8")
            truncated = len(content) > args.max_chars
            bounded = content[: args.max_chars]
            if truncated:
                bounded += "\n... [file content truncated by CodePilot]"
            return ToolResult(
                call_id=call.call_id,
                tool_name=self.name,
                status=ToolStatus.OK,
                output_summary=bounded,
                data={"path": context.workspace.display_path(path), "truncated": truncated},
                duration_ms=_elapsed_ms(start),
            )
        except WorkspaceViolation as error:
            return _denied(call, str(error), start)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            return _error(call, str(error), start)


class SearchTextInput(BaseModel):
    query: str = Field(min_length=1, max_length=200)
    path: str = "."
    max_matches: int = Field(default=50, ge=1, le=200)


class SearchTextTool(Tool):
    name = "search_text"
    description = "Search readable UTF-8 files for literal text within the workspace."
    input_model = SearchTextInput

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        start = time.perf_counter()
        try:
            args = self.input_model.model_validate(call.arguments)
            root = context.workspace.resolve(args.path)
            matches: list[dict[str, object]] = []
            for path in root.rglob("*"):
                if len(matches) >= args.max_matches or not path.is_file():
                    continue
                try:
                    context.workspace.resolve(context.workspace.display_path(path))
                    lines = path.read_text(encoding="utf-8").splitlines()
                except (OSError, UnicodeDecodeError, WorkspaceViolation):
                    continue
                for number, line in enumerate(lines, start=1):
                    if args.query in line:
                        matches.append(
                            {
                                "path": context.workspace.display_path(path),
                                "line": number,
                                "text": line[:300],
                            }
                        )
                    if len(matches) >= args.max_matches:
                        break
            summary = "\n".join(
                f"{item['path']}:{item['line']}: {item['text']}" for item in matches
            )
            return ToolResult(
                call_id=call.call_id,
                tool_name=self.name,
                status=ToolStatus.OK,
                output_summary=summary or "(no matches)",
                data={"matches": matches, "truncated": len(matches) >= args.max_matches},
                duration_ms=_elapsed_ms(start),
            )
        except WorkspaceViolation as error:
            return _denied(call, str(error), start)
        except ValueError as error:
            return _error(call, str(error), start)


class EditFileInput(BaseModel):
    path: str
    old_text: str = Field(min_length=1)
    new_text: str


class EditFileTool(Tool):
    name = "edit_file"
    description = "Replace exactly one literal text occurrence in a workspace file."
    input_model = EditFileInput

    def execute(self, call: ToolCall, context: ToolContext) -> ToolResult:
        start = time.perf_counter()
        try:
            args = self.input_model.model_validate(call.arguments)
            path = context.workspace.resolve(args.path, write=True)
            content = path.read_text(encoding="utf-8")
            occurrences = content.count(args.old_text)
            if occurrences != 1:
                return _error(
                    call,
                    f"Edit rejected: old_text must occur exactly once; found {occurrences}.",
                    start,
                )
            path.write_text(content.replace(args.old_text, args.new_text, 1), encoding="utf-8")
            return ToolResult(
                call_id=call.call_id,
                tool_name=self.name,
                status=ToolStatus.OK,
                output_summary=f"Updated {context.workspace.display_path(path)} with one exact replacement.",
                data={"path": context.workspace.display_path(path), "replacements": 1},
                duration_ms=_elapsed_ms(start),
            )
        except WorkspaceViolation as error:
            return _denied(call, str(error), start)
        except (OSError, UnicodeDecodeError, ValueError) as error:
            return _error(call, str(error), start)
