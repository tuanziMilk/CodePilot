from pathlib import Path

import pytest

from codepilot.environment.workspace import Workspace, WorkspaceViolation


def test_workspace_rejects_escape_and_protected_paths(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)

    with pytest.raises(WorkspaceViolation):
        workspace.resolve("../outside.py")
    with pytest.raises(WorkspaceViolation):
        workspace.resolve(".git/config")
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("hidden_tests/test_secret.py")
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("target/surefire-reports/result.txt")


def test_workspace_rejects_test_edits_and_non_allowlisted_edits(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path, allowed_write_paths=frozenset({"calculator.py"}))

    with pytest.raises(WorkspaceViolation):
        workspace.resolve("test_calculator.py", write=True)
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("other.py", write=True)
