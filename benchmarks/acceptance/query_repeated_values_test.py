from search_app.query import query_values
from search_app.request import search_request


def test_values_blanks_decoding_and_order():
    assert query_values("tag=&tag=a+b&tag=c%2Bd") == {"tag": ["", "a b", "c+d"]}
    assert query_values("a=1&b=2&a=3&empty") == {
        "a": ["1", "3"], "b": ["2"], "empty": [""]
    }
    assert query_values("%71=one&q=two") == {"q": ["one", "two"]}
    assert search_request("") == {"terms": [], "filters": []}
