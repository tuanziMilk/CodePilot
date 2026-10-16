import pytest
from networking.errors import RequestError
from networking.retry import request_with_retry


def test_transient_failure_then_success():
    outcomes = [RequestError("busy", transient=True), {"ok": True}]
    calls = []

    def operation():
        calls.append(1)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    assert request_with_retry(operation, 3) == {"ok": True}
    assert len(calls) == 2


def test_final_transient_error_is_reraised_at_exact_budget():
    calls = []

    def operation():
        calls.append(1)
        raise RequestError("busy", transient=True)

    with pytest.raises(RequestError, match="busy"):
        request_with_retry(operation, 2)
    assert len(calls) == 2


@pytest.mark.parametrize("budget", [0, -1])
def test_invalid_attempt_budget(budget):
    with pytest.raises(ValueError):
        request_with_retry(lambda: {"ok": True}, budget)
