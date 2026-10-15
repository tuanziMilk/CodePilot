import pytest

from codepilot.agent.harness import _is_test_command


@pytest.mark.parametrize(
    "command",
    [
        "python -m pytest -q",
        "pytest tests/unit -q",
        "mvn -o -pl common -Dtest=ResultFactoryTest test",
        "mvn --offline -q -pl common test -Dtest=ResultFactoryTest",
    ],
)
def test_supported_test_commands_are_detected(command: str) -> None:
    assert _is_test_command(command) is True


@pytest.mark.parametrize(
    "command",
    ["mvn -pl common -Dtest=ResultFactoryTest test", "mvn -o -pl common package", "git diff"],
)
def test_non_test_commands_are_not_detected(command: str) -> None:
    assert _is_test_command(command) is False
