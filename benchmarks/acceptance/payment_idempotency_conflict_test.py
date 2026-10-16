import pytest
from payments.errors import IdempotencyConflict
from payments.gateway import ScriptedGateway
from payments.service import PaymentService


def test_same_request_reuses_one_successful_gateway_call():
    gateway = ScriptedGateway([{"ok": True, "id": "p1"}])
    service = PaymentService(gateway)
    first = service.charge("order-1", 10)
    assert service.charge("order-1", 10) is first
    assert gateway.calls == [10]


def test_failure_is_not_cached_and_can_retry():
    gateway = ScriptedGateway([
        {"ok": False, "error": "temporary"},
        {"ok": True, "id": "p2"},
    ])
    service = PaymentService(gateway)
    assert service.charge("order-2", 20)["ok"] is False
    assert service.charge("order-2", 20) == {"ok": True, "id": "p2"}
    assert gateway.calls == [20, 20]


def test_conflict_does_not_call_gateway_again():
    gateway = ScriptedGateway([{"ok": True, "id": "p3"}])
    service = PaymentService(gateway)
    service.charge("order-3", 30)
    with pytest.raises(IdempotencyConflict):
        service.charge("order-3", 31)
    assert gateway.calls == [30]
