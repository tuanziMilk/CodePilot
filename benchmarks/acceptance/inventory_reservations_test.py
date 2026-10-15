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
