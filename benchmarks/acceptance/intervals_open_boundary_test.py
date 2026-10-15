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
