import pytest
from plugins_v2.errors import PluginNotFound
from plugins_v2.registry import Registry
from plugins_v2.resolver import resolve_plugin


def test_numeric_dotted_version_ordering():
    primary = Registry([
        {"name": "core", "version": "1.9.0", "entrypoint": "old"},
        {"name": "core", "version": "1.10.0", "entrypoint": "new"},
    ])
    assert resolve_plugin("core", primary, Registry())[
        "entrypoint"
    ] == "new"


def test_primary_namespace_shadows_newer_legacy_version():
    primary = Registry([
        {"name": "auth", "version": "1.0.0", "entrypoint": "primary"},
    ])
    legacy = Registry([
        {"name": "auth", "version": "99.0.0", "entrypoint": "legacy"},
    ])
    assert resolve_plugin("auth", primary, legacy)["entrypoint"] == "primary"


def test_legacy_fallback_and_optional_missing():
    legacy = Registry([
        {"name": "mail", "version": "3.0.0", "entrypoint": "legacy-mail"},
    ])
    assert resolve_plugin("mail", Registry(), legacy)["entrypoint"] == "legacy-mail"
    assert resolve_plugin("missing", Registry(), legacy, required=False) is None
    with pytest.raises(PluginNotFound):
        resolve_plugin("missing", Registry(), legacy)
