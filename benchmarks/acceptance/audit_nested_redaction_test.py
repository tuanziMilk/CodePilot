from copy import deepcopy
from audit.events import public_event
from audit.redaction import redact


def test_recursive_lists_case_and_primitives():
    payload = [
        [{"Token": "abc", "nested": [None, False, 0, {"PASSWORD": "xyz"}]}],
        "keep", [], {},
    ]
    original = deepcopy(payload)
    cleaned = redact(payload)
    assert cleaned == [
        [{"Token": "[REDACTED]", "nested": [
            None, False, 0, {"PASSWORD": "[REDACTED]"}
        ]}], "keep", [], {},
    ]
    assert payload == original
    assert public_event({"message": "token is a key, not a substring"})["payload"] == {
        "message": "token is a key, not a substring"
    }
