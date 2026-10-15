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
