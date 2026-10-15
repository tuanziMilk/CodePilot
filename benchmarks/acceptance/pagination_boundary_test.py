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
