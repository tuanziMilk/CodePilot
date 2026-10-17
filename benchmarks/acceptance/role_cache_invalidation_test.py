from authz.repository import RoleRepository
from authz.runtime import build_runtime


def test_only_changed_user_is_invalidated_and_event_shape_is_stable():
    repository = RoleRepository({"u-1": {"viewer"}, "u-2": {"admin"}})
    roles, permissions, bus, cache = build_runtime(repository)
    first = permissions.permissions_for("u-1")
    second = permissions.permissions_for("u-2")
    roles.set_roles("u-1", {"editor"})
    assert cache.invalidations == ["u-1"]
    assert cache.get("u-2") == second
    assert permissions.permissions_for("u-1") != first
    assert permissions.permissions_for("u-1") == frozenset({"read", "write"})
    assert bus.published == [("roles.changed", {
        "user_id": "u-1", "roles": ["editor"]
    })]


def test_setting_empty_roles_invalidates_previous_value():
    repository = RoleRepository({"u-3": {"admin"}})
    roles, permissions, _, cache = build_runtime(repository)
    assert "delete" in permissions.permissions_for("u-3")
    roles.set_roles("u-3", set())
    assert cache.get("u-3") is None
    assert permissions.permissions_for("u-3") == frozenset()
