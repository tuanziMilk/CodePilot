from settings_app.merge import merge_settings
from settings_app.startup import build_settings


def test_presence_not_truthiness():
    assert build_settings({"endpoint": None})["endpoint"] is None
    assert build_settings({})["retries"] == 3
    defaults = {"a": [1], "b": True}
    overrides = {"a": [], "new": False}
    merged = merge_settings(defaults, overrides)
    assert merged == {"a": [], "b": True, "new": False}
    assert defaults == {"a": [1], "b": True}
    assert overrides == {"a": [], "new": False}
