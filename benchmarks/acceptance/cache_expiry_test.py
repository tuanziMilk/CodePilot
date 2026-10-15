import pytest
from store.cache import TTLCache
from store.session import SessionStore


def test_lifetime_updates_and_falsy_values():
    clock = [3]
    cache = TTLCache(lambda: clock[0])
    cache.set("x", False, 2)
    clock[0] = 4
    assert cache.get("x") is False
    cache.set("x", 0, 4)
    clock[0] = 7
    assert cache.get("x") == 0
    clock[0] = 8
    assert cache.get("x", "missing") == "missing"
    assert cache.get("unknown", "missing") == "missing"


def test_zero_ttl_and_session_integration():
    cache = TTLCache(lambda: 20)
    sessions = SessionStore(cache)
    sessions.save("token", "Alice", 0)
    assert sessions.lookup("token") is None
    with pytest.raises(ValueError):
        cache.set("x", "value", -1)
