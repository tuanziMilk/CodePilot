"""Hard-v2 tasks with multi-file contracts and stronger external acceptance."""

from __future__ import annotations

from codepilot.benchmarks.definitions import BenchmarkTask, ReferenceEdit, source


def hard_task_definitions() -> tuple[BenchmarkTask, ...]:
    return (
        BenchmarkTask(
            "schema-alias-migration",
            "hard-v2",
            "multi-file-schema-compatibility",
            "Profile records are migrating from the legacy `name` field to `display_name`. "
            "Reads must accept either spelling, prefer `display_name` when both are present, "
            "and continue enforcing the existing required-value checks. Writes must emit only "
            "the canonical `display_name` field so a read/write round trip does not recreate "
            "legacy data. Preserve optional active=false values and do not mutate input payloads.",
            {
                "profiles_v2/__init__.py": "",
                "profiles_v2/errors.py": source('''
                    class ProfileFormatError(ValueError):
                        pass
                    '''),
                "profiles_v2/model.py": source('''
                    from dataclasses import dataclass


                    @dataclass(frozen=True)
                    class Profile:
                        profile_id: str
                        display_name: str
                        active: bool = True
                    '''),
                "profiles_v2/validation.py": source('''
                    from profiles_v2.errors import ProfileFormatError


                    def validate_payload(payload):
                        if not isinstance(payload, dict):
                            raise ProfileFormatError("profile payload must be an object")
                        if not payload.get("id"):
                            raise ProfileFormatError("profile id is required")
                    '''),
                "profiles_v2/codec_in.py": source('''
                    from profiles_v2.errors import ProfileFormatError
                    from profiles_v2.model import Profile
                    from profiles_v2.validation import validate_payload


                    def decode_profile(payload):
                        validate_payload(payload)
                        display_name = payload.get("display_name")
                        if not display_name:
                            raise ProfileFormatError("display name is required")
                        return Profile(
                            profile_id=payload["id"],
                            display_name=display_name,
                            active=payload.get("active", True),
                        )
                    '''),
                "profiles_v2/codec_out.py": source('''
                    def encode_profile(profile):
                        return {
                            "id": profile.profile_id,
                            "name": profile.display_name,
                            "active": profile.active,
                        }
                    '''),
                "profiles_v2/service.py": source('''
                    from profiles_v2.codec_in import decode_profile
                    from profiles_v2.codec_out import encode_profile


                    def normalize_record(payload):
                        return encode_profile(decode_profile(payload))
                    '''),
                "profiles_v2/storage.py": source('''
                    class ProfileStore:
                        def __init__(self):
                            self.records = {}

                        def put(self, profile_id, record):
                            self.records[profile_id] = dict(record)

                        def get(self, profile_id):
                            record = self.records.get(profile_id)
                            return dict(record) if record is not None else None
                    '''),
                "profiles_v2/api.py": source('''
                    from profiles_v2.service import normalize_record


                    def profile_response(payload):
                        return {"profile": normalize_record(payload)}
                    '''),
                "profiles_v2/audit.py": source('''
                    def audit_profile_change(profile_id, fields):
                        return {"profile_id": profile_id, "fields": sorted(fields)}
                    '''),
                "profiles_v2/legacy.py": source('''
                    def legacy_export(profile):
                        return {"id": profile.profile_id, "name": profile.display_name}
                    '''),
                "profiles_v2/fields.py": source('''
                    PROFILE_FIELDS = frozenset({"id", "display_name", "active"})
                    '''),
            },
            source('''
                from profiles_v2.codec_in import decode_profile
                from profiles_v2.codec_out import encode_profile


                def test_legacy_record_round_trips_to_canonical_schema():
                    profile = decode_profile({"id": "u-1", "name": "Ada", "active": False})
                    assert profile.display_name == "Ada"
                    assert encode_profile(profile) == {
                        "id": "u-1", "display_name": "Ada", "active": False
                    }
                '''),
            source('''
                import pytest
                from profiles_v2.codec_in import decode_profile
                from profiles_v2.codec_out import encode_profile
                from profiles_v2.errors import ProfileFormatError
                from profiles_v2.service import normalize_record


                def test_new_field_wins_and_input_is_unchanged():
                    payload = {
                        "id": "u-2", "name": "Legacy", "display_name": "Canonical",
                        "active": False,
                    }
                    original = dict(payload)
                    profile = decode_profile(payload)
                    assert profile.display_name == "Canonical"
                    assert profile.active is False
                    assert payload == original


                def test_normalization_never_recreates_legacy_alias():
                    assert normalize_record({"id": "u-3", "name": "Grace"}) == {
                        "id": "u-3", "display_name": "Grace", "active": True
                    }
                    assert "name" not in encode_profile(
                        decode_profile({"id": "u-4", "display_name": "Lin"})
                    )


                @pytest.mark.parametrize("payload", [
                    {}, {"id": "u-5"}, {"id": "u-5", "name": ""},
                    {"id": "u-5", "display_name": ""},
                ])
                def test_required_values_remain_enforced(payload):
                    with pytest.raises(ProfileFormatError):
                        decode_profile(payload)
                '''),
            "profiles_v2/codec_in.py",
            source('''
                def decode_profile(payload):
                    validate_payload(payload)
                    display_name = payload.get("display_name")
                    if not display_name:
                        raise ProfileFormatError("display name is required")
                    return Profile(
                        profile_id=payload["id"],
                        display_name=display_name,
                        active=payload.get("active", True),
                    )
                '''),
            source('''
                def decode_profile(payload):
                    validate_payload(payload)
                    if "display_name" in payload:
                        display_name = payload["display_name"]
                    else:
                        display_name = payload.get("name")
                    if not display_name:
                        raise ProfileFormatError("display name is required")
                    return Profile(
                        profile_id=payload["id"],
                        display_name=display_name,
                        active=payload.get("active", True),
                    )
                '''),
            additional_fixes=(ReferenceEdit(
                "profiles_v2/codec_out.py",
                '"name": profile.display_name,',
                '"display_name": profile.display_name,',
            ),),
        ),
        BenchmarkTask(
            "role-cache-invalidation",
            "hard-v2",
            "indirect-event-invalidation",
            "Permission checks continue returning stale values after a user's roles change. "
            "A role update must invalidate only that user's cached permissions through the "
            "existing event mechanism; unrelated users must remain cached. The public "
            "roles.changed payload is exactly {'user_id': user_id, 'roles': sorted_role_names}; "
            "preserve that schema and avoid clearing the entire cache.",
            {
                "authz/__init__.py": "",
                "authz/cache.py": source('''
                    class PermissionCache:
                        def __init__(self):
                            self.values = {}
                            self.invalidations = []

                        def get(self, user_id):
                            return self.values.get(user_id)

                        def set(self, user_id, permissions):
                            self.values[user_id] = frozenset(permissions)

                        def invalidate(self, user_id):
                            self.invalidations.append(user_id)
                            self.values.pop(user_id, None)
                    '''),
                "authz/events.py": source('''
                    class EventBus:
                        def __init__(self):
                            self.listeners = {}
                            self.published = []

                        def subscribe(self, event_name, listener):
                            self.listeners.setdefault(event_name, []).append(listener)

                        def publish(self, event_name, payload):
                            event = dict(payload)
                            self.published.append((event_name, event))
                            for listener in self.listeners.get(event_name, []):
                                listener(event)
                    '''),
                "authz/listeners.py": source('''
                    def register_cache_invalidation(bus, cache):
                        bus.subscribe(
                            "roles.changed",
                            lambda event: cache.invalidate(event["account_id"]),
                        )
                    '''),
                "authz/repository.py": source('''
                    class RoleRepository:
                        def __init__(self, initial=None):
                            self.values = {
                                user_id: set(roles) for user_id, roles in (initial or {}).items()
                            }

                        def roles_for(self, user_id):
                            return set(self.values.get(user_id, set()))

                        def save(self, user_id, roles):
                            self.values[user_id] = set(roles)
                    '''),
                "authz/roles.py": source('''
                    class RoleService:
                        def __init__(self, repository, bus):
                            self.repository = repository
                            self.bus = bus

                        def set_roles(self, user_id, roles):
                            normalized = set(roles)
                            self.repository.save(user_id, normalized)
                            return normalized
                    '''),
                "authz/permissions.py": source('''
                    ROLE_PERMISSIONS = {
                        "viewer": {"read"},
                        "editor": {"read", "write"},
                        "admin": {"read", "write", "delete"},
                    }


                    class PermissionService:
                        def __init__(self, repository, cache):
                            self.repository = repository
                            self.cache = cache

                        def permissions_for(self, user_id):
                            cached = self.cache.get(user_id)
                            if cached is not None:
                                return cached
                            permissions = set()
                            for role in self.repository.roles_for(user_id):
                                permissions.update(ROLE_PERMISSIONS.get(role, set()))
                            self.cache.set(user_id, permissions)
                            return frozenset(permissions)
                    '''),
                "authz/runtime.py": source('''
                    from authz.cache import PermissionCache
                    from authz.events import EventBus
                    from authz.listeners import register_cache_invalidation
                    from authz.permissions import PermissionService
                    from authz.roles import RoleService


                    def build_runtime(repository):
                        bus = EventBus()
                        cache = PermissionCache()
                        register_cache_invalidation(bus, cache)
                        return RoleService(repository, bus), PermissionService(repository, cache), bus, cache
                    '''),
                "authz/controller.py": source('''
                    def update_roles(role_service, user_id, roles):
                        return {"roles": sorted(role_service.set_roles(user_id, roles))}
                    '''),
                "authz/audit.py": source('''
                    def role_change_entry(user_id, before, after):
                        return {"user_id": user_id, "before": sorted(before), "after": sorted(after)}
                    '''),
                "authz/tokens.py": source('''
                    def token_subject(claims):
                        return claims.get("sub")
                    '''),
                "authz/legacy_cache.py": source('''
                    def clear_all_legacy_permissions(cache):
                        cache.clear()
                    '''),
            },
            source('''
                from authz.repository import RoleRepository
                from authz.runtime import build_runtime


                def test_role_change_invalidates_cached_permissions():
                    repository = RoleRepository({"u-1": {"viewer"}})
                    roles, permissions, _, _ = build_runtime(repository)
                    assert permissions.permissions_for("u-1") == frozenset({"read"})
                    roles.set_roles("u-1", {"editor"})
                    assert permissions.permissions_for("u-1") == frozenset({"read", "write"})
                '''),
            source('''
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
                '''),
            "authz/roles.py",
            source('''
                class RoleService:
                    def __init__(self, repository, bus):
                        self.repository = repository
                        self.bus = bus

                    def set_roles(self, user_id, roles):
                        normalized = set(roles)
                        self.repository.save(user_id, normalized)
                        return normalized
                '''),
            source('''
                class RoleService:
                    def __init__(self, repository, bus):
                        self.repository = repository
                        self.bus = bus

                    def set_roles(self, user_id, roles):
                        normalized = set(roles)
                        self.repository.save(user_id, normalized)
                        self.bus.publish("roles.changed", {
                            "user_id": user_id,
                            "roles": sorted(normalized),
                        })
                        return normalized
                '''),
            additional_fixes=(ReferenceEdit(
                "authz/listeners.py",
                'lambda event: cache.invalidate(event["account_id"]),',
                'lambda event: cache.invalidate(event["user_id"]),',
            ),),
        ),
        BenchmarkTask(
            "filtered-cursor-pagination",
            "hard-v2",
            "multi-file-pagination-contract",
            "Filtered catalog pagination is unstable: records can be returned out of id order, "
            "the item named by a cursor can appear again on the next page, and a final full page "
            "advertises a continuation that has no records. Use an exclusive cursor over stable "
            "id order, preserve filtering, reject invalid limits/cursors, and do not mutate records.",
            {
                "catalog_v2/__init__.py": "",
                "catalog_v2/errors.py": source('''
                    class CursorError(ValueError):
                        pass
                    '''),
                "catalog_v2/repository.py": source('''
                    class CatalogRepository:
                        def __init__(self, records):
                            self.records = [dict(record) for record in records]

                        def matching(self, category):
                            return [
                                dict(record) for record in self.records
                                if category is None or record.get("category") == category
                            ]
                    '''),
                "catalog_v2/cursor.py": source('''
                    from catalog_v2.errors import CursorError


                    def page_after(records, cursor, limit):
                        if limit < 1:
                            raise ValueError("limit must be positive")
                        ids = [record["id"] for record in records]
                        if cursor is None:
                            start = 0
                        else:
                            try:
                                start = ids.index(cursor)
                            except ValueError as error:
                                raise CursorError(cursor) from error
                        return records[start:start + limit]
                    '''),
                "catalog_v2/service.py": source('''
                    from catalog_v2.cursor import page_after


                    def list_products(repository, *, category=None, cursor=None, limit=20):
                        rows = repository.matching(category)
                        page = page_after(rows, cursor, limit)
                        next_cursor = page[-1]["id"] if len(page) == limit else None
                        return {"items": page, "next_cursor": next_cursor}
                    '''),
                "catalog_v2/controller.py": source('''
                    def catalog_response(service, **query):
                        return {"data": service(**query)}
                    '''),
                "catalog_v2/filtering.py": source('''
                    def active_only(records):
                        return [record for record in records if record.get("active", True)]
                    '''),
                "catalog_v2/sorting.py": source('''
                    def by_title(records):
                        return sorted(records, key=lambda record: record.get("title", ""))
                    '''),
                "catalog_v2/legacy_offset.py": source('''
                    def offset_page(records, offset, limit):
                        return records[offset:offset + limit]
                    '''),
                "catalog_v2/model.py": source('''
                    def product(product_id, category, title):
                        return {"id": product_id, "category": category, "title": title}
                    '''),
                "catalog_v2/metrics.py": source('''
                    def page_size(response):
                        return len(response["items"])
                    '''),
                "catalog_v2/export.py": source('''
                    def export_ids(records):
                        return [record["id"] for record in records]
                    '''),
            },
            source('''
                from catalog_v2.repository import CatalogRepository
                from catalog_v2.service import list_products


                def test_filtered_pages_are_stable_exclusive_and_end_cleanly():
                    repository = CatalogRepository([
                        {"id": "p-3", "category": "book"},
                        {"id": "p-1", "category": "book"},
                        {"id": "x-1", "category": "game"},
                        {"id": "p-2", "category": "book"},
                        {"id": "p-4", "category": "book"},
                    ])
                    first = list_products(repository, category="book", limit=2)
                    assert [item["id"] for item in first["items"]] == ["p-1", "p-2"]
                    second = list_products(
                        repository, category="book", cursor=first["next_cursor"], limit=2
                    )
                    assert [item["id"] for item in second["items"]] == ["p-3", "p-4"]
                    assert second["next_cursor"] is None
                '''),
            source('''
                import pytest
                from catalog_v2.errors import CursorError
                from catalog_v2.repository import CatalogRepository
                from catalog_v2.service import list_products


                def test_filtering_input_preservation_and_tail_page():
                    records = [
                        {"id": "b-2", "category": "book", "meta": {"stock": 1}},
                        {"id": "g-1", "category": "game", "meta": {"stock": 2}},
                        {"id": "b-1", "category": "book", "meta": {"stock": 3}},
                    ]
                    original = [dict(record) for record in records]
                    repository = CatalogRepository(records)
                    first = list_products(repository, category="book", limit=1)
                    second = list_products(
                        repository, category="book", cursor=first["next_cursor"], limit=1
                    )
                    assert [item["id"] for item in first["items"]] == ["b-1"]
                    assert [item["id"] for item in second["items"]] == ["b-2"]
                    assert second["next_cursor"] is None
                    assert records == original


                def test_invalid_limit_and_cursor_are_rejected():
                    repository = CatalogRepository([{"id": "p-1", "category": "book"}])
                    with pytest.raises(ValueError):
                        list_products(repository, limit=0)
                    with pytest.raises(CursorError):
                        list_products(repository, cursor="missing", limit=2)


                def test_empty_filter_has_no_cursor():
                    repository = CatalogRepository([{"id": "p-1", "category": "book"}])
                    assert list_products(repository, category="game", limit=2) == {
                        "items": [], "next_cursor": None
                    }
                '''),
            "catalog_v2/repository.py",
            source('''
                class CatalogRepository:
                    def __init__(self, records):
                        self.records = [dict(record) for record in records]

                    def matching(self, category):
                        return [
                            dict(record) for record in self.records
                            if category is None or record.get("category") == category
                        ]
                '''),
            source('''
                class CatalogRepository:
                    def __init__(self, records):
                        self.records = [dict(record) for record in records]

                    def matching(self, category):
                        matches = [
                            dict(record) for record in self.records
                            if category is None or record.get("category") == category
                        ]
                        return sorted(matches, key=lambda record: record["id"])
                '''),
            additional_fixes=(
                ReferenceEdit(
                    "catalog_v2/cursor.py",
                    "start = ids.index(cursor)",
                    "start = ids.index(cursor) + 1",
                ),
                ReferenceEdit(
                    "catalog_v2/service.py",
                    'next_cursor = page[-1]["id"] if len(page) == limit else None',
                    'next_cursor = (\n            page[-1]["id"]\n            if page and page[-1]["id"] != rows[-1]["id"]\n            else None\n        )',
                ),
            ),
        ),
        BenchmarkTask(
            "webhook-dedup-transaction",
            "hard-v2",
            "multi-file-idempotent-side-effect",
            "Webhook delivery tracking currently marks an event processed before its handler "
            "succeeds. A failed handler must leave no delivery record and must be retryable. "
            "After success, an identical delivery must return the original result without another "
            "handler call, while reuse of the same event id for a different payload must raise "
            "DeliveryConflict. Do not mutate payloads.",
            {
                "webhooks/__init__.py": "",
                "webhooks/errors.py": source('''
                    class DeliveryConflict(ValueError):
                        pass
                    '''),
                "webhooks/model.py": source('''
                    import hashlib
                    import json


                    def payload_digest(payload):
                        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                        return hashlib.sha256(encoded.encode()).hexdigest()
                    '''),
                "webhooks/store.py": source('''
                    class DeliveryStore:
                        def __init__(self):
                            self.records = {}

                        def get(self, event_id):
                            return self.records.get(event_id)

                        def mark_processed(self, event_id):
                            self.records[event_id] = True
                    '''),
                "webhooks/service.py": source('''
                    from webhooks.errors import DeliveryConflict
                    from webhooks.model import payload_digest


                    class WebhookService:
                        def __init__(self, store, handler):
                            self.store = store
                            self.handler = handler

                        def deliver(self, event_id, payload):
                            if self.store.get(event_id):
                                return {"status": "duplicate"}
                            self.store.mark_processed(event_id)
                            return self.handler.handle(payload)
                    '''),
                "webhooks/handler.py": source('''
                    class ScriptedHandler:
                        def __init__(self, outcomes):
                            self.outcomes = list(outcomes)
                            self.calls = []

                        def handle(self, payload):
                            self.calls.append(dict(payload))
                            outcome = self.outcomes.pop(0)
                            if isinstance(outcome, Exception):
                                raise outcome
                            return outcome
                    '''),
                "webhooks/router.py": source('''
                    def route_for(payload):
                        return payload.get("type", "unknown")
                    '''),
                "webhooks/signatures.py": source('''
                    def signature_header(headers):
                        return headers.get("X-Signature")
                    '''),
                "webhooks/audit.py": source('''
                    def delivery_entry(event_id, status):
                        return {"event_id": event_id, "status": status}
                    '''),
                "webhooks/metrics.py": source('''
                    def success_count(results):
                        return sum(bool(result.get("ok")) for result in results)
                    '''),
                "webhooks/queue.py": source('''
                    def enqueue(queue, event):
                        queue.append(dict(event))
                        return len(queue)
                    '''),
                "webhooks/legacy.py": source('''
                    def legacy_delivery_key(event_id, payload):
                        return f"{event_id}:{payload.get('type', 'unknown')}"
                    '''),
            },
            source('''
                import pytest
                from webhooks.handler import ScriptedHandler
                from webhooks.service import WebhookService
                from webhooks.store import DeliveryStore


                def test_failed_handler_can_retry_same_delivery():
                    handler = ScriptedHandler([RuntimeError("busy"), {"ok": True, "id": "r-1"}])
                    service = WebhookService(DeliveryStore(), handler)
                    with pytest.raises(RuntimeError, match="busy"):
                        service.deliver("evt-1", {"type": "created", "value": 3})
                    assert service.deliver("evt-1", {"type": "created", "value": 3}) == {
                        "ok": True, "id": "r-1"
                    }
                    assert len(handler.calls) == 2
                '''),
            source('''
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
                '''),
            "webhooks/store.py",
            source('''
                class DeliveryStore:
                    def __init__(self):
                        self.records = {}

                    def get(self, event_id):
                        return self.records.get(event_id)

                    def mark_processed(self, event_id):
                        self.records[event_id] = True
                '''),
            source('''
                class DeliveryStore:
                    def __init__(self):
                        self.records = {}

                    def get(self, event_id):
                        return self.records.get(event_id)

                    def mark_processed(self, event_id, digest, result):
                        self.records[event_id] = (digest, result)
                '''),
            additional_fixes=(ReferenceEdit(
                "webhooks/service.py",
                source('''
                    class WebhookService:
                        def __init__(self, store, handler):
                            self.store = store
                            self.handler = handler

                        def deliver(self, event_id, payload):
                            if self.store.get(event_id):
                                return {"status": "duplicate"}
                            self.store.mark_processed(event_id)
                            return self.handler.handle(payload)
                    '''),
                source('''
                    class WebhookService:
                        def __init__(self, store, handler):
                            self.store = store
                            self.handler = handler

                        def deliver(self, event_id, payload):
                            digest = payload_digest(payload)
                            record = self.store.get(event_id)
                            if record is not None:
                                previous_digest, result = record
                                if previous_digest != digest:
                                    raise DeliveryConflict(event_id)
                                return result
                            result = self.handler.handle(payload)
                            self.store.mark_processed(event_id, digest, result)
                            return result
                    '''),
            ),),
        ),
        BenchmarkTask(
            "plugin-resolution-shadowing",
            "hard-v2",
            "lexical-distractor-resolution",
            "Plugin resolution chooses a legacy implementation or version 2 over version 10. "
            "When the primary registry has candidates, select its highest numeric dotted version; "
            "only fall back to the legacy registry when primary has none. Missing optional plugins "
            "return None and missing required plugins still raise PluginNotFound.",
            {
                "plugins_v2/__init__.py": "",
                "plugins_v2/errors.py": source('''
                    class PluginNotFound(LookupError):
                        pass
                    '''),
                "plugins_v2/registry.py": source('''
                    class Registry:
                        def __init__(self, plugins=()):
                            self.plugins = [dict(plugin) for plugin in plugins]

                        def find(self, name):
                            matches = [plugin for plugin in self.plugins if plugin["name"] == name]
                            return sorted(matches, key=lambda plugin: plugin["version"], reverse=True)
                    '''),
                "plugins_v2/resolver.py": source('''
                    from plugins_v2.errors import PluginNotFound


                    def resolve_plugin(name, primary, legacy, *, required=True):
                        candidates = legacy.find(name) + primary.find(name)
                        if not candidates:
                            if required:
                                raise PluginNotFound(name)
                            return None
                        return candidates[0]
                    '''),
                "plugins_v2/discovery.py": source('''
                    def discover(manifests):
                        return [dict(manifest) for manifest in manifests if manifest.get("enabled", True)]
                    '''),
                "plugins_v2/manifest.py": source('''
                    def plugin_manifest(name, version, entrypoint, *, enabled=True):
                        return {
                            "name": name, "version": version,
                            "entrypoint": entrypoint, "enabled": enabled,
                        }
                    '''),
                "plugins_v2/loader.py": source('''
                    def load_entrypoint(plugin, available):
                        return available[plugin["entrypoint"]]
                    '''),
                "plugins_v2/runtime.py": source('''
                    from plugins_v2.loader import load_entrypoint
                    from plugins_v2.resolver import resolve_plugin


                    def activate(name, primary, legacy, available):
                        return load_entrypoint(resolve_plugin(name, primary, legacy), available)
                    '''),
                "plugins_v2/legacy_registry.py": source('''
                    def legacy_names(registry):
                        return sorted({plugin["name"] for plugin in registry.plugins})
                    '''),
                "plugins_v2/compat.py": source('''
                    def major_version(plugin):
                        return int(plugin["version"].split(".", 1)[0])
                    '''),
                "plugins_v2/defaults.py": source('''
                    DEFAULT_PLUGIN = "core"
                    '''),
                "plugins_v2/audit.py": source('''
                    def resolution_entry(name, plugin):
                        return {"name": name, "resolved": plugin and plugin["entrypoint"]}
                    '''),
                "plugins_v2/config.py": source('''
                    def configured_plugins(settings):
                        return list(settings.get("plugins", []))
                    '''),
            },
            source('''
                from plugins_v2.registry import Registry
                from plugins_v2.resolver import resolve_plugin


                def test_primary_highest_numeric_version_wins_over_legacy():
                    primary = Registry([
                        {"name": "search", "version": "2.0.0", "entrypoint": "primary-v2"},
                        {"name": "search", "version": "10.0.0", "entrypoint": "primary-v10"},
                    ])
                    legacy = Registry([
                        {"name": "search", "version": "9.0.0", "entrypoint": "legacy-v9"},
                    ])
                    assert resolve_plugin("search", primary, legacy)["entrypoint"] == "primary-v10"
                '''),
            source('''
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
                '''),
            "plugins_v2/registry.py",
            source('''
                class Registry:
                    def __init__(self, plugins=()):
                        self.plugins = [dict(plugin) for plugin in plugins]

                    def find(self, name):
                        matches = [plugin for plugin in self.plugins if plugin["name"] == name]
                        return sorted(matches, key=lambda plugin: plugin["version"], reverse=True)
                '''),
            source('''
                def _version_key(plugin):
                    return tuple(int(part) for part in plugin["version"].split("."))


                class Registry:
                    def __init__(self, plugins=()):
                        self.plugins = [dict(plugin) for plugin in plugins]

                    def find(self, name):
                        matches = [plugin for plugin in self.plugins if plugin["name"] == name]
                        return sorted(matches, key=_version_key, reverse=True)
                '''),
            additional_fixes=(ReferenceEdit(
                "plugins_v2/resolver.py",
                "candidates = legacy.find(name) + primary.find(name)",
                "candidates = primary.find(name) + legacy.find(name)",
            ),),
        ),
        BenchmarkTask(
            "ledger-transfer-atomicity",
            "hard-v2",
            "multi-file-atomic-idempotency",
            "Ledger transfers can leave a debit entry behind when the destination account is "
            "invalid, and idempotency keys can silently reuse a result for a different transfer. "
            "Validate the complete transfer before appending entries, append the debit and credit "
            "as one batch, remember only successful requests, return an equal result for identical "
            "successful retries without appending entries, and reject conflicting key reuse with "
            "TransferConflict.",
            {
                "ledger/__init__.py": "",
                "ledger/errors.py": source('''
                    class AccountNotFound(LookupError):
                        pass


                    class InsufficientFunds(ValueError):
                        pass


                    class TransferConflict(ValueError):
                        pass
                    '''),
                "ledger/accounts.py": source('''
                    from ledger.errors import AccountNotFound


                    class AccountStore:
                        def __init__(self, balances):
                            self.balances = dict(balances)

                        def balance(self, account_id):
                            try:
                                return self.balances[account_id]
                            except KeyError as error:
                                raise AccountNotFound(account_id) from error
                    '''),
                "ledger/journal.py": source('''
                    class Journal:
                        def __init__(self):
                            self.entries = []

                        def append(self, entry):
                            if entry["amount"] <= 0:
                                raise ValueError("entry amount must be positive")
                            self.entries.append(dict(entry))

                        def append_many(self, entries):
                            pending = [dict(entry) for entry in entries]
                            if any(entry["amount"] <= 0 for entry in pending):
                                raise ValueError("entry amount must be positive")
                            self.entries.extend(pending)
                    '''),
                "ledger/idempotency.py": source('''
                    class RequestLog:
                        def __init__(self):
                            self.records = {}

                        def lookup(self, key):
                            return self.records.get(key)

                        def remember(self, key, result):
                            self.records[key] = result
                    '''),
                "ledger/service.py": source('''
                    from ledger.errors import InsufficientFunds, TransferConflict


                    class TransferService:
                        def __init__(self, accounts, journal, requests):
                            self.accounts = accounts
                            self.journal = journal
                            self.requests = requests

                        def transfer(self, key, source_id, target_id, amount):
                            cached = self.requests.lookup(key)
                            if cached is not None:
                                return cached
                            if amount <= 0:
                                raise ValueError("amount must be positive")
                            source_balance = self.accounts.balance(source_id)
                            if source_balance < amount:
                                raise InsufficientFunds(source_id)
                            self.journal.append({
                                "account_id": source_id, "kind": "debit", "amount": amount
                            })
                            self.accounts.balance(target_id)
                            self.journal.append({
                                "account_id": target_id, "kind": "credit", "amount": amount
                            })
                            result = {"source": source_id, "target": target_id, "amount": amount}
                            self.requests.remember(key, result)
                            return result
                    '''),
                "ledger/reporting.py": source('''
                    def account_entries(journal, account_id):
                        return [
                            entry for entry in journal.entries
                            if entry["account_id"] == account_id
                        ]
                    '''),
                "ledger/audit.py": source('''
                    def transfer_entry(key, result):
                        return {"key": key, **result}
                    '''),
                "ledger/controller.py": source('''
                    def transfer_response(service, request):
                        result = service.transfer(
                            request["key"], request["source"], request["target"], request["amount"]
                        )
                        return {"transfer": result}
                    '''),
                "ledger/balances.py": source('''
                    def projected_balance(opening, entries, account_id):
                        value = opening
                        for entry in entries:
                            if entry["account_id"] == account_id:
                                value += entry["amount"] if entry["kind"] == "credit" else -entry["amount"]
                        return value
                    '''),
                "ledger/legacy.py": source('''
                    def legacy_transfer_id(source_id, target_id):
                        return f"{source_id}:{target_id}"
                    '''),
                "ledger/model.py": source('''
                    def transfer_request(source_id, target_id, amount):
                        return (source_id, target_id, amount)
                    '''),
                "ledger/metrics.py": source('''
                    def transfer_count(journal):
                        return len(journal.entries) // 2
                    '''),
            },
            source('''
                import pytest
                from ledger.accounts import AccountStore
                from ledger.errors import AccountNotFound, TransferConflict
                from ledger.idempotency import RequestLog
                from ledger.journal import Journal
                from ledger.service import TransferService


                def test_invalid_target_is_atomic_and_key_can_retry():
                    journal = Journal()
                    service = TransferService(
                        AccountStore({"source": 50}), journal, RequestLog()
                    )
                    with pytest.raises(AccountNotFound):
                        service.transfer("req-1", "source", "missing", 10)
                    assert journal.entries == []


                def test_conflicting_key_is_rejected():
                    service = TransferService(
                        AccountStore({"a": 50, "b": 0}), Journal(), RequestLog()
                    )
                    service.transfer("req-2", "a", "b", 10)
                    with pytest.raises(TransferConflict):
                        service.transfer("req-2", "a", "b", 11)
                '''),
            source('''
                import pytest
                from ledger.accounts import AccountStore
                from ledger.errors import AccountNotFound, InsufficientFunds, TransferConflict
                from ledger.idempotency import RequestLog
                from ledger.journal import Journal
                from ledger.service import TransferService


                def make_service(balances):
                    journal = Journal()
                    requests = RequestLog()
                    return TransferService(AccountStore(balances), journal, requests), journal, requests


                def test_success_appends_one_atomic_pair_and_duplicate_reuses_result():
                    service, journal, _ = make_service({"a": 50, "b": 0})
                    first = service.transfer("req-3", "a", "b", 12)
                    assert service.transfer("req-3", "a", "b", 12) == first
                    assert journal.entries == [
                        {"account_id": "a", "kind": "debit", "amount": 12},
                        {"account_id": "b", "kind": "credit", "amount": 12},
                    ]


                def test_failed_requests_leave_no_entries_or_idempotency_record():
                    service, journal, requests = make_service({"a": 5})
                    with pytest.raises(AccountNotFound):
                        service.transfer("missing", "a", "b", 2)
                    with pytest.raises(InsufficientFunds):
                        service.transfer("poor", "a", "a", 8)
                    with pytest.raises(ValueError):
                        service.transfer("invalid", "a", "a", 0)
                    assert journal.entries == []
                    assert requests.records == {}


                def test_key_conflicts_cover_every_request_field():
                    service, journal, _ = make_service({"a": 50, "b": 0, "c": 0})
                    service.transfer("same", "a", "b", 10)
                    for request in [("a", "b", 11), ("a", "c", 10), ("c", "b", 10)]:
                        with pytest.raises(TransferConflict):
                            service.transfer("same", *request)
                    assert len(journal.entries) == 2
                '''),
            "ledger/idempotency.py",
            source('''
                class RequestLog:
                    def __init__(self):
                        self.records = {}

                    def lookup(self, key):
                        return self.records.get(key)

                    def remember(self, key, result):
                        self.records[key] = result
                '''),
            source('''
                class RequestLog:
                    def __init__(self):
                        self.records = {}

                    def lookup(self, key):
                        return self.records.get(key)

                    def remember(self, key, request, result):
                        self.records[key] = (request, result)
                '''),
            additional_fixes=(ReferenceEdit(
                "ledger/service.py",
                source('''
                    class TransferService:
                        def __init__(self, accounts, journal, requests):
                            self.accounts = accounts
                            self.journal = journal
                            self.requests = requests

                        def transfer(self, key, source_id, target_id, amount):
                            cached = self.requests.lookup(key)
                            if cached is not None:
                                return cached
                            if amount <= 0:
                                raise ValueError("amount must be positive")
                            source_balance = self.accounts.balance(source_id)
                            if source_balance < amount:
                                raise InsufficientFunds(source_id)
                            self.journal.append({
                                "account_id": source_id, "kind": "debit", "amount": amount
                            })
                            self.accounts.balance(target_id)
                            self.journal.append({
                                "account_id": target_id, "kind": "credit", "amount": amount
                            })
                            result = {"source": source_id, "target": target_id, "amount": amount}
                            self.requests.remember(key, result)
                            return result
                    '''),
                source('''
                    class TransferService:
                        def __init__(self, accounts, journal, requests):
                            self.accounts = accounts
                            self.journal = journal
                            self.requests = requests

                        def transfer(self, key, source_id, target_id, amount):
                            request = (source_id, target_id, amount)
                            cached = self.requests.lookup(key)
                            if cached is not None:
                                previous_request, result = cached
                                if previous_request != request:
                                    raise TransferConflict(key)
                                return result
                            if amount <= 0:
                                raise ValueError("amount must be positive")
                            source_balance = self.accounts.balance(source_id)
                            self.accounts.balance(target_id)
                            if source_balance < amount:
                                raise InsufficientFunds(source_id)
                            entries = [
                                {"account_id": source_id, "kind": "debit", "amount": amount},
                                {"account_id": target_id, "kind": "credit", "amount": amount},
                            ]
                            self.journal.append_many(entries)
                            result = {"source": source_id, "target": target_id, "amount": amount}
                            self.requests.remember(key, request, result)
                            return result
                    '''),
            ),),
        ),
    )
