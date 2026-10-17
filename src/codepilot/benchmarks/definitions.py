"""Small original tasks; reference edits and acceptance tests never enter agent repos."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


def source(value: str) -> str:
    return dedent(value).lstrip("\n")


@dataclass(frozen=True)
class ReferenceEdit:
    path: str
    old: str
    new: str


@dataclass(frozen=True)
class BenchmarkTask:
    task_id: str
    difficulty: str
    family: str
    issue: str
    files: dict[str, str]
    visible_test: str
    acceptance_test: str
    fix_path: str
    old: str
    new: str
    additional_fixes: tuple[ReferenceEdit, ...] = ()

    def reference_edits(self) -> tuple[ReferenceEdit, ...]:
        return (ReferenceEdit(self.fix_path, self.old, self.new), *self.additional_fixes)

    def reference_source(self) -> str:
        content = self.files[self.fix_path]
        if content.count(self.old) != 1:
            raise ValueError(f"Reference edit must have one match: {self.task_id}")
        return content.replace(self.old, self.new, 1)


def base_task_definitions() -> tuple[BenchmarkTask, ...]:
    return (
        BenchmarkTask(
            "addition-smoke", "smoke", "arithmetic",
            "The calculator's addition operation returns an incorrect result for positive "
            "integers. Restore addition behavior without changing the other operations.",
            {"calculator.py": source('''
                def add(a, b):
                    return a - b


                def subtract(a, b):
                    return a - b
                ''')},
            source('''
                from calculator import add, subtract


                def test_addition_and_subtraction():
                    assert add(2, 3) == 5
                    assert subtract(7, 2) == 5
                '''),
            source('''
                import pytest
                from calculator import add, subtract


                @pytest.mark.parametrize("a,b", [(0, 0), (-4, 7), (-2, -8), (100, 3)])
                def test_addition_generalizes(a, b):
                    assert add(a, b) == a + b
                    assert subtract(a, b) == a - b
                '''),
            "calculator.py", "return a - b\n\n\ndef subtract", "return a + b\n\n\ndef subtract",
        ),
        BenchmarkTask(
            "email-case", "easy", "normalization",
            "Address normalization corrupts case-sensitive mailbox names. Trim surrounding "
            "whitespace and lowercase the domain only; preserve mailbox spelling and the "
            "existing invalid-address behavior.",
            {"email_utils.py": source('''
                def normalize_email(address):
                    address = address.strip()
                    if address.count("@") != 1:
                        raise ValueError("Expected one @ separator")
                    mailbox, domain = address.split("@")
                    if not mailbox or not domain:
                        raise ValueError("Mailbox and domain are required")
                    return f"{mailbox.lower()}@{domain.lower()}"
                ''')},
            source('''
                from email_utils import normalize_email


                def test_preserve_mailbox():
                    assert normalize_email("  Alice.Sales@EXAMPLE.COM  ") == "Alice.Sales@example.com"
                '''),
            source('''
                import pytest
                from email_utils import normalize_email


                @pytest.mark.parametrize("address,expected", [
                    ("a+b@Example.Org", "a+b@example.org"),
                    (" USER@DOMAIN ", "USER@domain"),
                    ("mixed.Case@lower", "mixed.Case@lower"),
                ])
                def test_normalization(address, expected):
                    assert normalize_email(address) == expected


                @pytest.mark.parametrize("address", ["missing", "a@@b", "@b", "a@"])
                def test_invalid_addresses(address):
                    with pytest.raises(ValueError):
                        normalize_email(address)
                '''),
            "email_utils.py", "{mailbox.lower()}@{domain.lower()}", "{mailbox}@{domain.lower()}",
        ),
        BenchmarkTask(
            "pagination-boundary", "easy", "boundary",
            "A list endpoint returns one fewer item than requested and loses records between "
            "pages. Page numbers start at 1; each page should contain up to page_size items. "
            "Keep validation of nonpositive page and page_size values.",
            {"pagination.py": source('''
                def paginate(items, page, page_size):
                    if page < 1 or page_size < 1:
                        raise ValueError("page and page_size must be positive")
                    start = (page - 1) * page_size
                    end = start + page_size - 1
                    return items[start:end]
                ''')},
            source('''
                from pagination import paginate


                def test_first_two_pages():
                    assert paginate(list(range(7)), 1, 3) == [0, 1, 2]
                    assert paginate(list(range(7)), 2, 3) == [3, 4, 5]
                '''),
            source('''
                import pytest
                from pagination import paginate


                def test_tail_empty_and_single_item_pages():
                    assert paginate(list(range(7)), 3, 3) == [6]
                    assert paginate([9], 1, 1) == [9]
                    assert paginate([], 1, 4) == []
                    assert paginate([1, 2], 3, 2) == []


                @pytest.mark.parametrize("page,size", [(0, 2), (-1, 2), (1, 0)])
                def test_validation(page, size):
                    with pytest.raises(ValueError):
                        paginate([], page, size)
                '''),
            "pagination.py", "end = start + page_size - 1", "end = start + page_size",
        ),
        BenchmarkTask(
            "cache-expiry", "medium", "state-boundary",
            "A cached value is still returned exactly at its expiration timestamp. The "
            "contract says a value is valid only while now < expires_at. Preserve cache "
            "updates, missing-key behavior, and the injected clock used by tests.",
            {
                "store/__init__.py": "",
                "store/clock.py": source('''
                    import time


                    def now_seconds():
                        return time.monotonic()
                    '''),
                "store/cache.py": source('''
                    from store.clock import now_seconds


                    class TTLCache:
                        def __init__(self, clock=now_seconds):
                            self.clock = clock
                            self.entries = {}

                        def set(self, key, value, ttl):
                            if ttl < 0:
                                raise ValueError("ttl must be nonnegative")
                            self.entries[key] = (value, self.clock() + ttl)

                        def get(self, key, default=None):
                            if key not in self.entries:
                                return default
                            value, expires_at = self.entries[key]
                            if self.clock() > expires_at:
                                del self.entries[key]
                                return default
                            return value
                    '''),
                "store/session.py": source('''
                    class SessionStore:
                        def __init__(self, cache):
                            self.cache = cache

                        def save(self, token, user, ttl):
                            self.cache.set(token, user, ttl)

                        def lookup(self, token):
                            return self.cache.get(token)
                    '''),
            },
            source('''
                from store.cache import TTLCache


                def test_expiration_boundary():
                    clock = [10]
                    cache = TTLCache(lambda: clock[0])
                    cache.set("user", "Alice", 5)
                    clock[0] = 15
                    assert cache.get("user") is None
                '''),
            source('''
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
                '''),
            "store/cache.py", "self.clock() > expires_at", "self.clock() >= expires_at",
        ),
        BenchmarkTask(
            "inventory-reservations", "medium", "multifile-localization",
            "Checkout can oversell an item when the cart contains the same SKU on multiple "
            "lines. Reservation totals must sum quantities across all lines, and reject a "
            "checkout when a total exceeds stock. Keep independent SKUs independent.",
            {
                "shop/__init__.py": "",
                "shop/catalog.py": source('''
                    def product(sku, stock):
                        if stock < 0:
                            raise ValueError("Stock cannot be negative")
                        return {"sku": sku, "stock": stock}
                    '''),
                "shop/reservations.py": source('''
                    def reservation_totals(lines):
                        totals = {}
                        for line in lines:
                            sku, quantity = line["sku"], line["quantity"]
                            if quantity <= 0:
                                raise ValueError("Quantity must be positive")
                            totals[sku] = quantity
                        return totals
                    '''),
                "shop/checkout.py": source('''
                    from shop.reservations import reservation_totals


                    def checkout(lines, stock):
                        totals = reservation_totals(lines)
                        if any(quantity > stock.get(sku, 0) for sku, quantity in totals.items()):
                            raise ValueError("Insufficient stock")
                        return {sku: stock[sku] - quantity for sku, quantity in totals.items()}
                    '''),
                "shop/shipping.py": source('''
                    def shipping_units(lines):
                        return sum(line["quantity"] for line in lines)
                    '''),
            },
            source('''
                import pytest
                from shop.checkout import checkout


                def test_duplicate_sku_cannot_oversell():
                    lines = [{"sku": "tea", "quantity": 3}, {"sku": "tea", "quantity": 3}]
                    with pytest.raises(ValueError, match="Insufficient stock"):
                        checkout(lines, {"tea": 5})
                '''),
            source('''
                import pytest
                from shop.checkout import checkout
                from shop.reservations import reservation_totals


                def test_duplicate_lines_and_multiple_skus():
                    lines = [
                        {"sku": "tea", "quantity": 2},
                        {"sku": "rice", "quantity": 1},
                        {"sku": "tea", "quantity": 4},
                    ]
                    assert reservation_totals(lines) == {"tea": 6, "rice": 1}
                    assert checkout(lines, {"tea": 8, "rice": 4}) == {"tea": 2, "rice": 3}
                    assert checkout([], {}) == {}


                def test_invalid_quantity_still_rejected():
                    with pytest.raises(ValueError):
                        checkout([{"sku": "tea", "quantity": 0}], {"tea": 3})
                    with pytest.raises(ValueError):
                        checkout([{"sku": "unknown", "quantity": 1}], {})
                '''),
            "shop/reservations.py", "totals[sku] = quantity", "totals[sku] = totals.get(sku, 0) + quantity",
        ),
        BenchmarkTask(
            "config-falsy-overrides", "medium", "configuration",
            "Explicit configuration overrides such as false, 0, and an empty string are "
            "ignored in favor of defaults. An override must win whenever its key is present, "
            "including an explicit null. Fall back only when that key is absent.",
            {
                "settings_app/__init__.py": "",
                "settings_app/defaults.py": source('''
                    DEFAULTS = {"debug": True, "retries": 3, "prefix": "app", "endpoint": "local"}
                    '''),
                "settings_app/merge.py": source('''
                    def merge_settings(defaults, overrides):
                        result = defaults.copy()
                        for key in overrides:
                            result[key] = overrides.get(key) or defaults.get(key)
                        return result
                    '''),
                "settings_app/startup.py": source('''
                    from settings_app.defaults import DEFAULTS
                    from settings_app.merge import merge_settings


                    def build_settings(overrides):
                        return merge_settings(DEFAULTS, overrides)
                    '''),
                "settings_app/display.py": source('''
                    def display_settings(settings):
                        return "\\n".join(f"{key}={value}" for key, value in sorted(settings.items()))
                    '''),
            },
            source('''
                from settings_app.startup import build_settings


                def test_explicit_falsy_overrides():
                    settings = build_settings({"debug": False, "retries": 0, "prefix": ""})
                    assert settings["debug"] is False
                    assert settings["retries"] == 0
                    assert settings["prefix"] == ""
                '''),
            source('''
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
                '''),
            "settings_app/merge.py", "overrides.get(key) or defaults.get(key)", "overrides[key]",
        ),
        BenchmarkTask(
            "intervals-open-boundary", "medium", "algorithm-boundary",
            "The scheduling report combines adjacent reservations, even though half-open "
            "intervals [start, end) that only touch are separate reservations. Merge genuinely "
            "overlapping intervals, preserve adjacency, and leave the caller's input unchanged.",
            {
                "scheduling/__init__.py": "",
                "scheduling/intervals.py": source('''
                    def merge_overlaps(intervals):
                        merged = []
                        for start, end in sorted(intervals):
                            if start >= end:
                                raise ValueError("Intervals must have positive length")
                            if merged and start <= merged[-1][1]:
                                merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                            else:
                                merged.append((start, end))
                        return merged
                    '''),
                "scheduling/report.py": source('''
                    from scheduling.intervals import merge_overlaps


                    def reservation_summary(intervals):
                        groups = merge_overlaps(intervals)
                        return {"groups": groups, "occupied": sum(end - start for start, end in groups)}
                    '''),
                "scheduling/calendar.py": source('''
                    def day_key(year, month, day):
                        return f"{year:04d}-{month:02d}-{day:02d}"
                    '''),
            },
            source('''
                from scheduling.report import reservation_summary


                def test_adjacent_bookings_stay_separate():
                    assert reservation_summary([(1, 3), (3, 5)])["groups"] == [(1, 3), (3, 5)]
                '''),
            source('''
                import pytest
                from scheduling.intervals import merge_overlaps
                from scheduling.report import reservation_summary


                def test_overlap_nesting_and_input_preservation():
                    original = [(8, 10), (1, 5), (2, 4), (4, 7), (7, 8)]
                    before = list(original)
                    assert merge_overlaps(original) == [(1, 7), (7, 8), (8, 10)]
                    assert original == before
                    assert reservation_summary([(1, 4), (2, 6)])["occupied"] == 5
                    assert merge_overlaps([]) == []


                def test_invalid_interval():
                    with pytest.raises(ValueError):
                        merge_overlaps([(2, 2)])
                '''),
            "scheduling/intervals.py", "start <= merged[-1][1]", "start < merged[-1][1]",
        ),
        BenchmarkTask(
            "money-half-up", "medium", "decimal-rounding",
            "Invoice totals round an exact half-cent downward, contrary to the billing "
            "contract: apply a percentage discount using decimal arithmetic and round the "
            "final amount to two places with ROUND_HALF_UP. Keep rate validation and do not "
            "round each line separately.",
            {
                "billing/__init__.py": "",
                "billing/money.py": source('''
                    from decimal import Decimal, ROUND_HALF_EVEN, ROUND_HALF_UP


                    def discounted_total(amount, percent):
                        amount, percent = Decimal(str(amount)), Decimal(str(percent))
                        if not 0 <= percent <= 100:
                            raise ValueError("Discount must be between 0 and 100")
                        total = amount * (Decimal("1") - percent / Decimal("100"))
                        return total.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
                    '''),
                "billing/invoice.py": source('''
                    from decimal import Decimal
                    from billing.money import discounted_total


                    def invoice_total(lines, percent=0):
                        subtotal = sum((Decimal(str(price)) * quantity for price, quantity in lines),
                                       start=Decimal("0"))
                        return discounted_total(subtotal, percent)
                    '''),
                "billing/formatting.py": source('''
                    def format_currency(amount, symbol="$"):
                        return f"{symbol}{amount:.2f}"
                    '''),
            },
            source('''
                from decimal import Decimal
                from billing.invoice import invoice_total


                def test_half_cent_uses_billing_rounding():
                    assert invoice_total([("1.00", 1)], percent=1.5) == Decimal("0.99")
                '''),
            source('''
                from decimal import Decimal
                import pytest
                from billing.invoice import invoice_total
                from billing.money import discounted_total


                def test_round_once_after_aggregation():
                    assert invoice_total([("0.005", 1), ("0.005", 1)]) == Decimal("0.01")
                    assert discounted_total("2.345", 0) == Decimal("2.35")
                    assert discounted_total("100", 100) == Decimal("0.00")
                    assert invoice_total([], 0) == Decimal("0.00")


                @pytest.mark.parametrize("rate", [-1, 101])
                def test_invalid_discount(rate):
                    with pytest.raises(ValueError):
                        discounted_total("10", rate)
                '''),
            "billing/money.py", "rounding=ROUND_HALF_EVEN", "rounding=ROUND_HALF_UP",
        ),
        BenchmarkTask(
            "audit-nested-redaction", "hard", "recursive-structure",
            "Audit events redact credentials in nested objects but leak them when those "
            "objects occur inside arrays. Apply the same case-insensitive password/token "
            "redaction recursively through dictionaries and lists. Preserve array order, "
            "ordinary values, and the original event object.",
            {
                "audit/__init__.py": "",
                "audit/redaction.py": source('''
                    SECRET_KEYS = {"password", "token"}


                    def redact(value):
                        if isinstance(value, dict):
                            return {
                                key: "[REDACTED]" if key.lower() in SECRET_KEYS else redact(item)
                                for key, item in value.items()
                            }
                        if isinstance(value, list):
                            return list(value)
                        return value
                    '''),
                "audit/events.py": source('''
                    from audit.redaction import redact


                    def public_event(payload):
                        return {"kind": "audit", "payload": redact(payload)}
                    '''),
                "audit/formatting.py": source('''
                    import json


                    def format_event(event):
                        return json.dumps(event, sort_keys=True)
                    '''),
                "audit/transport.py": source('''
                    def collect_event(event, output):
                        output.append(event)
                        return len(output)
                    '''),
            },
            source('''
                from audit.events import public_event


                def test_redact_array_objects():
                    payload = {"users": [{"name": "Alice", "password": "secret"}]}
                    event = public_event(payload)
                    assert event["payload"]["users"][0]["password"] == "[REDACTED]"
                    assert payload["users"][0]["password"] == "secret"
                '''),
            source('''
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
                '''),
            "audit/redaction.py", "return list(value)", "return [redact(item) for item in value]",
        ),
        BenchmarkTask(
            "query-repeated-values", "hard", "multifile-integration",
            "Repeated query parameters lose all but the last value in generated search "
            "requests. Preserve every value in encounter order, including blanks, and "
            "continue percent-decoding keys/values. The request API maps each key to a list.",
            {
                "search_app/__init__.py": "",
                "search_app/query.py": source('''
                    from urllib.parse import parse_qsl


                    def query_values(raw_query):
                        values = {}
                        for key, value in parse_qsl(raw_query, keep_blank_values=True):
                            values[key] = [value]
                        return values
                    '''),
                "search_app/request.py": source('''
                    from search_app.query import query_values


                    def search_request(raw_query):
                        params = query_values(raw_query)
                        return {"terms": params.get("q", []), "filters": params.get("tag", [])}
                    '''),
                "search_app/ranking.py": source('''
                    def rank_documents(documents, terms):
                        return sorted(documents, key=lambda text: sum(text.count(t) for t in terms),
                                      reverse=True)
                    '''),
                "search_app/render.py": source('''
                    def render_results(results):
                        return [{"position": index, "text": text}
                                for index, text in enumerate(results, start=1)]
                    '''),
                "search_app/history.py": source('''
                    def record_query(history, raw_query):
                        history.append(raw_query)
                        return len(history)
                    '''),
            },
            source('''
                from search_app.request import search_request


                def test_multiple_filter_values():
                    request = search_request("q=tea&tag=green&tag=loose")
                    assert request == {"terms": ["tea"], "filters": ["green", "loose"]}
                '''),
            source('''
                from search_app.query import query_values
                from search_app.request import search_request


                def test_values_blanks_decoding_and_order():
                    assert query_values("tag=&tag=a+b&tag=c%2Bd") == {"tag": ["", "a b", "c+d"]}
                    assert query_values("a=1&b=2&a=3&empty") == {
                        "a": ["1", "3"], "b": ["2"], "empty": [""]
                    }
                    assert query_values("%71=one&q=two") == {"q": ["one", "two"]}
                    assert search_request("") == {"terms": [], "filters": []}
                '''),
            "search_app/query.py", "values[key] = [value]", "values.setdefault(key, []).append(value)",
        ),
        BenchmarkTask(
            "atomic-batch-reservation", "challenge", "transactional-state",
            "A failed batch reservation can leave earlier stock rows decremented. Treat the "
            "whole batch atomically, combine duplicate SKU quantities before checking stock, "
            "reject nonpositive quantities, and preserve the existing successful return shape.",
            {
                "warehouse/__init__.py": "",
                "warehouse/errors.py": source('''
                    class InvalidQuantity(ValueError):
                        pass


                    class InsufficientStock(ValueError):
                        pass
                    '''),
                "warehouse/inventory.py": source('''
                    from warehouse.errors import InsufficientStock, InvalidQuantity


                    def reserve_batch(stock, lines):
                        reserved = {}
                        for sku, quantity in lines:
                            if quantity <= 0:
                                raise InvalidQuantity(sku)
                            available = stock.get(sku, 0)
                            if available < quantity:
                                raise InsufficientStock(sku)
                            stock[sku] = available - quantity
                            reserved[sku] = reserved.get(sku, 0) + quantity
                        return reserved
                    '''),
                "warehouse/checkout.py": source('''
                    from warehouse.inventory import reserve_batch
                    from warehouse.receipts import reservation_receipt


                    def checkout(stock, lines):
                        return reservation_receipt(reserve_batch(stock, lines))
                    '''),
                "warehouse/receipts.py": source('''
                    def reservation_receipt(reserved):
                        return {"items": dict(sorted(reserved.items())), "units": sum(reserved.values())}
                    '''),
                "warehouse/catalog.py": source('''
                    def available_skus(stock):
                        return sorted(sku for sku, quantity in stock.items() if quantity > 0)
                    '''),
            },
            source('''
                import pytest
                from warehouse.errors import InsufficientStock
                from warehouse.inventory import reserve_batch


                def test_failed_batch_rolls_back_earlier_rows():
                    stock = {"tea": 2, "cup": 1}
                    with pytest.raises(InsufficientStock):
                        reserve_batch(stock, [("tea", 1), ("cup", 2)])
                    assert stock == {"tea": 2, "cup": 1}
                '''),
            source('''
                import pytest
                from warehouse.checkout import checkout
                from warehouse.errors import InsufficientStock, InvalidQuantity
                from warehouse.inventory import reserve_batch


                def test_duplicate_skus_are_validated_as_one_atomic_request():
                    stock = {"tea": 2}
                    with pytest.raises(InsufficientStock):
                        reserve_batch(stock, [("tea", 1), ("tea", 2)])
                    assert stock == {"tea": 2}


                def test_success_preserves_shape_and_inputs():
                    stock = {"tea": 5, "cup": 2}
                    lines = [("tea", 1), ("cup", 1), ("tea", 2)]
                    assert checkout(stock, lines) == {
                        "items": {"cup": 1, "tea": 3}, "units": 4
                    }
                    assert stock == {"tea": 2, "cup": 1}
                    assert lines == [("tea", 1), ("cup", 1), ("tea", 2)]


                @pytest.mark.parametrize("lines,error", [
                    ([("missing", 1)], InsufficientStock),
                    ([("tea", 0)], InvalidQuantity),
                    ([("tea", -1)], InvalidQuantity),
                ])
                def test_invalid_batches_do_not_mutate(lines, error):
                    stock = {"tea": 2}
                    with pytest.raises(error):
                        reserve_batch(stock, lines)
                    assert stock == {"tea": 2}
                '''),
            "warehouse/inventory.py",
            source('''
                def reserve_batch(stock, lines):
                    reserved = {}
                    for sku, quantity in lines:
                        if quantity <= 0:
                            raise InvalidQuantity(sku)
                        available = stock.get(sku, 0)
                        if available < quantity:
                            raise InsufficientStock(sku)
                        stock[sku] = available - quantity
                        reserved[sku] = reserved.get(sku, 0) + quantity
                    return reserved
                '''),
            source('''
                def reserve_batch(stock, lines):
                    reserved = {}
                    for sku, quantity in lines:
                        if quantity <= 0:
                            raise InvalidQuantity(sku)
                        reserved[sku] = reserved.get(sku, 0) + quantity
                    for sku, quantity in reserved.items():
                        if stock.get(sku, 0) < quantity:
                            raise InsufficientStock(sku)
                    for sku, quantity in reserved.items():
                        stock[sku] -= quantity
                    return reserved
                '''),
        ),
        BenchmarkTask(
            "dependency-cycle-order", "challenge", "graph-invariant",
            "Deployment planning silently accepts dependency cycles. Return each dependency "
            "before its consumer in stable manifest order, include dependency-only nodes once, "
            "and raise DependencyCycleError for any reachable cycle.",
            {
                "deploy/__init__.py": "",
                "deploy/errors.py": source('''
                    class DependencyCycleError(ValueError):
                        pass
                    '''),
                "deploy/planner.py": source('''
                    from deploy.errors import DependencyCycleError


                    def deployment_order(graph, roots):
                        visited = set()
                        order = []

                        def visit(node):
                            if node in visited:
                                return
                            visited.add(node)
                            for dependency in graph.get(node, []):
                                visit(dependency)
                            order.append(node)

                        for root in roots:
                            visit(root)
                        return order
                    '''),
                "deploy/manifest.py": source('''
                    def dependency_graph(entries):
                        return {entry["name"]: list(entry.get("depends_on", [])) for entry in entries}
                    '''),
                "deploy/runner.py": source('''
                    from deploy.manifest import dependency_graph
                    from deploy.planner import deployment_order


                    def plan_manifest(entries, roots):
                        return deployment_order(dependency_graph(entries), roots)
                    '''),
                "deploy/render.py": source('''
                    def render_plan(order):
                        return " -> ".join(order)
                    '''),
            },
            source('''
                import pytest
                from deploy.errors import DependencyCycleError
                from deploy.planner import deployment_order


                def test_reachable_cycle_is_rejected():
                    with pytest.raises(DependencyCycleError):
                        deployment_order({"api": ["db"], "db": ["api"]}, ["api"])
                '''),
            source('''
                import pytest
                from deploy.errors import DependencyCycleError
                from deploy.planner import deployment_order


                def test_shared_and_dependency_only_nodes_are_stable():
                    graph = {"api": ["db", "cache"], "db": ["network"], "cache": ["network"]}
                    original = {key: list(value) for key, value in graph.items()}
                    assert deployment_order(graph, ["api"]) == ["network", "db", "cache", "api"]
                    assert graph == original


                def test_multiple_roots_are_not_duplicated():
                    assert deployment_order({"web": ["core"], "worker": ["core"]},
                                            ["web", "worker"]) == ["core", "web", "worker"]


                def test_self_and_deep_cycles_raise():
                    with pytest.raises(DependencyCycleError):
                        deployment_order({"a": ["a"]}, ["a"])
                    with pytest.raises(DependencyCycleError):
                        deployment_order({"a": ["b"], "b": ["c"], "c": ["b"]}, ["a"])
                '''),
            "deploy/planner.py",
            source('''
                def deployment_order(graph, roots):
                    visited = set()
                    order = []

                    def visit(node):
                        if node in visited:
                            return
                        visited.add(node)
                        for dependency in graph.get(node, []):
                            visit(dependency)
                        order.append(node)

                    for root in roots:
                        visit(root)
                    return order
                '''),
            source('''
                def deployment_order(graph, roots):
                    complete = set()
                    active = set()
                    order = []

                    def visit(node):
                        if node in active:
                            raise DependencyCycleError(node)
                        if node in complete:
                            return
                        active.add(node)
                        for dependency in graph.get(node, []):
                            visit(dependency)
                        active.remove(node)
                        complete.add(node)
                        order.append(node)

                    for root in roots:
                        visit(root)
                    return order
                '''),
        ),
        BenchmarkTask(
            "payment-idempotency-conflict", "challenge", "stateful-idempotency",
            "Payment idempotency keys currently return a cached success even when reused for a "
            "different amount, and failed gateway responses become permanently cached. Reuse a "
            "successful response only for the same amount; reject conflicts and allow failures to retry.",
            {
                "payments/__init__.py": "",
                "payments/errors.py": source('''
                    class IdempotencyConflict(ValueError):
                        pass
                    '''),
                "payments/gateway.py": source('''
                    class ScriptedGateway:
                        def __init__(self, responses):
                            self.responses = list(responses)
                            self.calls = []

                        def charge(self, amount):
                            self.calls.append(amount)
                            return self.responses.pop(0)
                    '''),
                "payments/service.py": source('''
                    from payments.errors import IdempotencyConflict


                    class PaymentService:
                        def __init__(self, gateway):
                            self.gateway = gateway
                            self._responses = {}

                        def charge(self, key, amount):
                            if key in self._responses:
                                return self._responses[key]
                            response = self.gateway.charge(amount)
                            self._responses[key] = response
                            return response
                    '''),
                "payments/receipts.py": source('''
                    def receipt(response):
                        return {"payment_id": response.get("id"), "accepted": bool(response.get("ok"))}
                    '''),
                "payments/audit.py": source('''
                    def audit_entry(key, amount):
                        return {"key": key, "amount": amount}
                    '''),
            },
            source('''
                import pytest
                from payments.errors import IdempotencyConflict
                from payments.gateway import ScriptedGateway
                from payments.service import PaymentService


                def test_key_reuse_with_different_amount_is_rejected():
                    service = PaymentService(ScriptedGateway([{"ok": True, "id": "p1"}]))
                    service.charge("order-1", 10)
                    with pytest.raises(IdempotencyConflict):
                        service.charge("order-1", 11)
                '''),
            source('''
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
                '''),
            "payments/service.py",
            source('''
                class PaymentService:
                    def __init__(self, gateway):
                        self.gateway = gateway
                        self._responses = {}

                    def charge(self, key, amount):
                        if key in self._responses:
                            return self._responses[key]
                        response = self.gateway.charge(amount)
                        self._responses[key] = response
                        return response
                '''),
            source('''
                class PaymentService:
                    def __init__(self, gateway):
                        self.gateway = gateway
                        self._records = {}

                    def charge(self, key, amount):
                        if key in self._records:
                            previous_amount, response = self._records[key]
                            if previous_amount != amount:
                                raise IdempotencyConflict(key)
                            return response
                        response = self.gateway.charge(amount)
                        if response.get("ok"):
                            self._records[key] = (amount, response)
                        return response
                '''),
        ),
        BenchmarkTask(
            "profile-event-versioning", "challenge", "event-projection",
            "Profile events may arrive out of order or be delivered twice. Build the projection "
            "in contiguous version order starting at 1, ignore identical duplicates, reject "
            "conflicting duplicates or gaps, and do not mutate event payloads.",
            {
                "profiles/__init__.py": "",
                "profiles/errors.py": source('''
                    class ProjectionError(ValueError):
                        pass
                    '''),
                "profiles/projector.py": source('''
                    from profiles.errors import ProjectionError


                    def project_profile(events):
                        state = {"version": 0}
                        for event in events:
                            state.update(event["changes"])
                            state["version"] = event["version"]
                        return state
                    '''),
                "profiles/events.py": source('''
                    def profile_event(version, **changes):
                        return {"version": version, "changes": changes}
                    '''),
                "profiles/render.py": source('''
                    def display_name(profile):
                        return profile.get("display_name", "anonymous")
                    '''),
                "profiles/store.py": source('''
                    def append_event(stream, event):
                        stream.append(event)
                        return len(stream)
                    '''),
            },
            source('''
                from profiles.projector import project_profile


                def test_out_of_order_events_use_version_order():
                    events = [
                        {"version": 2, "changes": {"plan": "pro"}},
                        {"version": 1, "changes": {"display_name": "Ada"}},
                    ]
                    assert project_profile(events) == {
                        "version": 2, "display_name": "Ada", "plan": "pro"
                    }
                '''),
            source('''
                from copy import deepcopy
                import pytest
                from profiles.errors import ProjectionError
                from profiles.projector import project_profile


                def test_identical_duplicates_are_idempotent_and_input_is_unchanged():
                    events = [
                        {"version": 2, "changes": {"plan": "pro"}},
                        {"version": 1, "changes": {"display_name": "Ada"}},
                        {"version": 2, "changes": {"plan": "pro"}},
                    ]
                    original = deepcopy(events)
                    assert project_profile(events) == {
                        "version": 2, "display_name": "Ada", "plan": "pro"
                    }
                    assert events == original


                def test_conflicts_and_gaps_are_rejected():
                    with pytest.raises(ProjectionError):
                        project_profile([
                            {"version": 1, "changes": {"plan": "free"}},
                            {"version": 1, "changes": {"plan": "pro"}},
                        ])
                    with pytest.raises(ProjectionError):
                        project_profile([{"version": 2, "changes": {"plan": "pro"}}])


                def test_empty_stream_has_zero_version():
                    assert project_profile([]) == {"version": 0}
                '''),
            "profiles/projector.py",
            source('''
                def project_profile(events):
                    state = {"version": 0}
                    for event in events:
                        state.update(event["changes"])
                        state["version"] = event["version"]
                    return state
                '''),
            source('''
                def project_profile(events):
                    by_version = {}
                    for event in events:
                        version = event["version"]
                        changes = dict(event["changes"])
                        if version in by_version and by_version[version] != changes:
                            raise ProjectionError(version)
                        by_version[version] = changes
                    state = {"version": 0}
                    for expected, version in enumerate(sorted(by_version), start=1):
                        if version != expected:
                            raise ProjectionError(version)
                        state.update(by_version[version])
                        state["version"] = version
                    return state
                '''),
        ),
        BenchmarkTask(
            "retry-error-classification", "challenge", "retry-policy",
            "The request helper retries permanent failures and can silently return None after "
            "exhausting transient failures. Validate max_attempts, retry only transient errors, "
            "return the first success, and re-raise the final error after exactly the budgeted calls.",
            {
                "networking/__init__.py": "",
                "networking/errors.py": source('''
                    class RequestError(RuntimeError):
                        def __init__(self, message, *, transient):
                            super().__init__(message)
                            self.transient = transient
                    '''),
                "networking/retry.py": source('''
                    from networking.errors import RequestError


                    def request_with_retry(operation, max_attempts):
                        for attempt in range(max_attempts):
                            try:
                                return operation()
                            except RequestError:
                                if attempt == max_attempts:
                                    raise
                    '''),
                "networking/client.py": source('''
                    from networking.retry import request_with_retry


                    def fetch_json(transport, path, max_attempts=3):
                        return request_with_retry(lambda: transport.get(path), max_attempts)
                    '''),
                "networking/transport.py": source('''
                    class ScriptedTransport:
                        def __init__(self, outcomes):
                            self.outcomes = list(outcomes)
                            self.calls = []

                        def get(self, path):
                            self.calls.append(path)
                            outcome = self.outcomes.pop(0)
                            if isinstance(outcome, Exception):
                                raise outcome
                            return outcome
                    '''),
                "networking/metrics.py": source('''
                    def attempt_count(transport):
                        return len(transport.calls)
                    '''),
            },
            source('''
                import pytest
                from networking.errors import RequestError
                from networking.retry import request_with_retry


                def test_permanent_error_is_not_retried():
                    calls = []

                    def operation():
                        calls.append(1)
                        raise RequestError("bad request", transient=False)

                    with pytest.raises(RequestError):
                        request_with_retry(operation, 3)
                    assert len(calls) == 1
                '''),
            source('''
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
                '''),
            "networking/retry.py",
            source('''
                def request_with_retry(operation, max_attempts):
                    for attempt in range(max_attempts):
                        try:
                            return operation()
                        except RequestError:
                            if attempt == max_attempts:
                                raise
                '''),
            source('''
                def request_with_retry(operation, max_attempts):
                    if max_attempts < 1:
                        raise ValueError("max_attempts must be positive")
                    for attempt in range(max_attempts):
                        try:
                            return operation()
                        except RequestError as error:
                            if not error.transient or attempt == max_attempts - 1:
                                raise
                '''),
        ),
    )


def task_definitions() -> tuple[BenchmarkTask, ...]:
    """Return the regression tasks followed by the frozen hard-v2 suite."""

    from codepilot.benchmarks.hard_definitions import hard_task_definitions

    return (*base_task_definitions(), *hard_task_definitions())
