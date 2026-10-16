import pytest

from codepilot.permissions.policy import PermissionDenied, PermissionPolicy


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .",
        "pytest -q && ls",
        "git reset --hard",
        "mvn -pl common -Dtest=ResultFactoryTest test",
        "mvn -o -pl common clean test",
        'python -c "print(1)"',
    ],
)
def test_dangerous_or_composed_commands_are_denied(command: str) -> None:
    with pytest.raises(PermissionDenied):
        PermissionPolicy("test-v1").authorize_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q",
        "git diff",
        "git diff --check",
        "git diff --stat --name-only",
        "git status --short",
        "pwd",
        "mvn -o -pl common -Dtest=ResultFactoryTest test",
        "mvn --offline -q -pl common test -Dtest=ResultFactoryTest",
    ],
)
def test_allowed_phase1_commands(command: str) -> None:
    PermissionPolicy("test-v1").authorize_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "git status --ignored",
        "git diff --cached",
        "git diff --output=report.txt",
        "mvn -o -pl common test -Dtest=ResultFactoryTest -DfailIfNoTests=false",
        "mvn -o -pl common test verify",
    ],
)
def test_unlisted_git_or_maven_variants_are_denied(command: str) -> None:
    with pytest.raises(PermissionDenied):
        PermissionPolicy("test-v1").authorize_command(command)
