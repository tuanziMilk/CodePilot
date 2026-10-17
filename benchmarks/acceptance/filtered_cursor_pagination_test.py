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
