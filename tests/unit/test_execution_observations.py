from types import SimpleNamespace

import pytest

from codepilot.agent.harness import AgentHarness, RunState
from codepilot.environment.git_bash import ProcessResult
from codepilot.models.protocol import ToolCall, ToolResult, ToolStatus
from codepilot.permissions.policy import PermissionPolicy
from codepilot.tools.bash import BashTool
from codepilot.tools.dispatcher import ToolDispatcher
from codepilot.verification.runner import VerificationRunner


def test_completed_failed_command_without_output_reports_return_code() -> None:
    context = SimpleNamespace(
        permissions=PermissionPolicy("test"),
        environment=SimpleNamespace(run=lambda *_: ProcessResult("", "", 1, 10)),
        command_timeout_seconds=30,
    )
    call = ToolCall(call_id="test", name="bash", arguments={"command": "python -m pytest -q"})

    result = BashTool().execute(call, context)

    assert result.status is ToolStatus.OK
    assert result.return_code == 1
    assert "Status: ok" in result.output_summary
    assert "Return code: 1" in result.output_summary
    assert "no output" in result.output_summary


@pytest.mark.parametrize(
    ("status", "return_code", "expected"),
    [(ToolStatus.OK, 1, True), (ToolStatus.OK, 0, False),
     (ToolStatus.TIMEOUT, 1, False), (ToolStatus.ERROR, 1, False),
     (ToolStatus.DENIED, None, False)],
)
def test_only_completed_failed_tests_unlock_reproduction(status, return_code, expected) -> None:
    state = RunState(messages=[])
    call = ToolCall(call_id="test", name="bash", arguments={"command": "python -m pytest -q"})
    result = ToolResult(
        call_id="test", tool_name="bash", status=status,
        output_summary="", return_code=return_code, duration_ms=0,
    )
    AgentHarness._observe_test_failure(state, call, result)
    assert state.reproduction_failure_observed is expected


def test_verifier_adapter_exception_returns_explicit_failure() -> None:
    def broken_run(*_):
        raise OSError("process unavailable")

    verifier = VerificationRunner(
        SimpleNamespace(run=broken_run), PermissionPolicy("test"), timeout_seconds=30,
    )
    result = verifier.verify("python -m pytest -q")

    assert result.passed is False
    assert result.return_code is None
    assert result.failure_kind == "execution_error"
    assert "process unavailable" in result.output_summary


def test_verifier_timeout_is_distinct_from_failed_assertion() -> None:
    verifier = VerificationRunner(
        SimpleNamespace(run=lambda *_: ProcessResult("", "", None, 30, timed_out=True)),
        PermissionPolicy("test"), timeout_seconds=30,
    )
    result = verifier.verify("python -m pytest -q")
    assert result.passed is False
    assert result.failure_kind == "timeout"
    assert "timed out" in result.output_summary


def test_dispatcher_error_retains_elapsed_time(monkeypatch) -> None:
    def broken_execute(*_):
        raise RuntimeError("adapter broke")

    elapsed_clock = iter([10.0, 10.123])
    monkeypatch.setattr("codepilot.tools.dispatcher.perf_counter", lambda: next(elapsed_clock))
    dispatcher = ToolDispatcher(
        [SimpleNamespace(name="broken", execute=broken_execute)], SimpleNamespace(),
    )
    result = dispatcher.execute(ToolCall(call_id="1", name="broken"))
    assert result.status is ToolStatus.ERROR
    assert result.duration_ms == 123
    assert "adapter broke" in result.output_summary
