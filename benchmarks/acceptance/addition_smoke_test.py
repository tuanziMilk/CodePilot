import pytest
from calculator import add, subtract


@pytest.mark.parametrize("a,b", [(0, 0), (-4, 7), (-2, -8), (100, 3)])
def test_addition_generalizes(a, b):
    assert add(a, b) == a + b
    assert subtract(a, b) == a - b
