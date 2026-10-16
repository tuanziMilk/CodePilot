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
