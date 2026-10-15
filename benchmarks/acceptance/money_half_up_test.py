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
