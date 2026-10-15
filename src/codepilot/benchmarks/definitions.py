"""Small original tasks; reference edits and acceptance tests never enter agent repos."""

from __future__ import annotations

from dataclasses import dataclass
from textwrap import dedent


def source(value: str) -> str:
    return dedent(value).lstrip("\n")


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

    def reference_source(self) -> str:
        content = self.files[self.fix_path]
        if content.count(self.old) != 1:
            raise ValueError(f"Reference edit must have one match: {self.task_id}")
        return content.replace(self.old, self.new, 1)


def task_definitions() -> tuple[BenchmarkTask, ...]:
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
    )
