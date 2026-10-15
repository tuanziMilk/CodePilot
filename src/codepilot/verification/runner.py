"""Verification command execution and explicit success result."""

from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from codepilot.environment.git_bash import GitBashEnvironment
from codepilot.permissions.policy import PermissionDenied, PermissionPolicy


@dataclass(frozen=True)
class VerificationResult:
    passed: bool
    command: str
    output_summary: str
    return_code: int | None
    duration_ms: int
    failure_kind: str | None = None


class VerificationRunner:
    def __init__(
        self,
        environment: GitBashEnvironment,
        permissions: PermissionPolicy,
        timeout_seconds: float,
    ) -> None:
        self._environment = environment
        self._permissions = permissions
        self._timeout_seconds = timeout_seconds

    def verify(self, command: str) -> VerificationResult:
        """Run the declared test and return an explicit result even on adapter faults."""

        started = perf_counter()
        try:
            self._permissions.authorize_command(command)
            result = self._environment.run(command, self._timeout_seconds)
        except Exception as error:  # noqa: BLE001 - verifier faults are failed observations.
            return VerificationResult(
                passed=False,
                command=command,
                output_summary=f"Verification could not execute: {type(error).__name__}: {error}",
                return_code=None,
                duration_ms=round((perf_counter() - started) * 1000),
                failure_kind=(
                    "permission_denied" if isinstance(error, PermissionDenied) else "execution_error"
                ),
            )
        output = result.stdout
        if result.stderr:
            output = f"{output}\n[stderr]\n{result.stderr}".strip()
        passed = not result.timed_out and result.return_code == 0
        if result.timed_out:
            output = f"Verification timed out.\n{output}".strip()
        return VerificationResult(
            passed=passed,
            command=command,
            output_summary=(
                f"Return code: {result.return_code}\n"
                f"{output or '(verification command produced no output)'}"
            ),
            return_code=result.return_code,
            duration_ms=result.duration_ms,
            failure_kind=None if passed else ("timeout" if result.timed_out else "test_failed"),
        )

