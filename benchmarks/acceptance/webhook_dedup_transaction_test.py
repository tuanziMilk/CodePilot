from copy import deepcopy
import pytest
from webhooks.errors import DeliveryConflict
from webhooks.handler import ScriptedHandler
from webhooks.service import WebhookService
from webhooks.store import DeliveryStore


def test_success_is_reused_without_another_side_effect():
    handler = ScriptedHandler([{"ok": True, "id": "r-2"}])
    service = WebhookService(DeliveryStore(), handler)
    payload = {"type": "updated", "nested": {"value": 4}}
    original = deepcopy(payload)
    first = service.deliver("evt-2", payload)
    assert service.deliver("evt-2", payload) == first
    assert handler.calls == [payload]
    assert payload == original


def test_conflicting_payload_is_rejected_without_handler_call():
    handler = ScriptedHandler([{"ok": True}])
    service = WebhookService(DeliveryStore(), handler)
    service.deliver("evt-3", {"value": 1})
    with pytest.raises(DeliveryConflict):
        service.deliver("evt-3", {"value": 2})
    assert len(handler.calls) == 1


def test_failed_delivery_leaves_no_record():
    store = DeliveryStore()
    service = WebhookService(store, ScriptedHandler([RuntimeError("down")]))
    with pytest.raises(RuntimeError):
        service.deliver("evt-4", {"value": 1})
    assert store.get("evt-4") is None
