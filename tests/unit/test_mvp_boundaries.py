from pathlib import Path

import pytest

from codepilot.config.settings import Settings
from codepilot.environment.workspace import Workspace, WorkspaceViolation
from codepilot.permissions.policy import PermissionDenied, PermissionPolicy


@pytest.mark.parametrize("command", [
    "ls ../", "rg --files /", "rg sentinel", "python -m pytest ../outside.py",
    "python -m pytest --override-ini=pythonpath=..", "pytest -q\npwd",
    "pytest -q & pwd", "pytest $TESTS", "python -m pytest -p malicious",
    "python -m pytest {..,..}/external_test.py", "python -m pytest ~/external_test.py",
    "python -m pytest *", "mvn -o -pl .. test",
])
def test_bash_rejects_escape_expansion_and_unlisted_pytest_options(command: str) -> None:
    with pytest.raises(PermissionDenied):
        PermissionPolicy("mvp-v1").authorize_command(command)


def test_workspace_protects_env_and_explicitly_forbidden_files(tmp_path: Path) -> None:
    workspace = Workspace(
        tmp_path,
        allowed_write_paths=frozenset({"core.py"}),
        forbidden_write_paths=frozenset({"core.py"}),
    )
    with pytest.raises(WorkspaceViolation):
        workspace.resolve(".env")
    with pytest.raises(WorkspaceViolation):
        workspace.resolve(".env.local")
    with pytest.raises(WorkspaceViolation):
        workspace.resolve("core.py", write=True)


def test_settings_rejects_endpoint_with_embedded_secret() -> None:
    with pytest.raises(ValueError, match="credentials"):
        Settings(llm_model="test", llm_api_key="not-real", llm_base_url="https://user:secret@example.com")
