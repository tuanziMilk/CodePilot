"""Canonical workspace-boundary checks shared by file tools."""

from __future__ import annotations

from pathlib import Path, PureWindowsPath


class WorkspaceViolation(ValueError):
    """Raised when a requested path would escape or access a protected area."""


class Workspace:
    """The one repository location a Phase-1 Agent is allowed to inspect."""

    DEFAULT_PROTECTED_PARTS = frozenset(
        {
            ".git",
            ".codepilot",
            "hidden_tests",
            "verifier",
            "evaluation_metadata",
            "target",
            "node_modules",
            ".venv",
            "__pycache__",
            ".pytest_cache",
            ".env",
        }
    )

    def __init__(
        self,
        root: Path,
        protected_parts: frozenset[str] | None = None,
        allowed_write_paths: frozenset[str] | None = None,
        forbidden_write_paths: frozenset[str] = frozenset(),
    ) -> None:
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError(f"Workspace root is not a directory: {self.root}")
        self.protected_parts = protected_parts or self.DEFAULT_PROTECTED_PARTS
        self.allowed_write_paths = allowed_write_paths
        self.forbidden_write_paths = frozenset(
            value.replace("\\", "/").casefold() for value in forbidden_write_paths
        )

    def resolve(self, relative_path: str, *, write: bool = False) -> Path:
        candidate = Path(relative_path)
        if candidate.is_absolute() or PureWindowsPath(relative_path).drive:
            raise WorkspaceViolation("Absolute paths are not accepted; use a workspace-relative path.")

        resolved = (self.root / candidate).resolve()
        try:
            relative = resolved.relative_to(self.root)
        except ValueError as error:
            raise WorkspaceViolation("Path escapes the configured workspace.") from error

        if any(
            part.lower() in self.protected_parts or part.lower().startswith(".env.")
            for part in relative.parts
        ):
            action = "write" if write else "read"
            raise WorkspaceViolation(f"Policy denies {action} access to protected path: {relative}")
        if write:
            normalized = relative.as_posix()
            if normalized.casefold() in self.forbidden_write_paths:
                raise WorkspaceViolation(f"Policy denies editing task forbidden_files: {normalized}")
            if self.allowed_write_paths is not None and normalized not in self.allowed_write_paths:
                raise WorkspaceViolation(f"Policy denies edits outside task allowed_files: {normalized}")
            if self.allowed_write_paths is None and self._looks_like_test_path(relative):
                raise WorkspaceViolation(
                    f"Policy denies editing test-like path without an explicit allowed_files rule: {normalized}"
                )
        return resolved

    def display_path(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    @staticmethod
    def _looks_like_test_path(relative: Path) -> bool:
        return relative.name.startswith("test_") or any(part.lower() == "tests" for part in relative.parts)
