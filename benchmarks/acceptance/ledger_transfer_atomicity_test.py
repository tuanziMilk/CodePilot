import pytest
from ledger.accounts import AccountStore
from ledger.errors import AccountNotFound, InsufficientFunds, TransferConflict
from ledger.idempotency import RequestLog
from ledger.journal import Journal
from ledger.service import TransferService


def make_service(balances):
    journal = Journal()
    requests = RequestLog()
    return TransferService(AccountStore(balances), journal, requests), journal, requests


def test_success_appends_one_atomic_pair_and_duplicate_reuses_result():
    service, journal, _ = make_service({"a": 50, "b": 0})
    first = service.transfer("req-3", "a", "b", 12)
    assert service.transfer("req-3", "a", "b", 12) == first
    assert journal.entries == [
        {"account_id": "a", "kind": "debit", "amount": 12},
        {"account_id": "b", "kind": "credit", "amount": 12},
    ]


def test_failed_requests_leave_no_entries_or_idempotency_record():
    service, journal, requests = make_service({"a": 5})
    with pytest.raises(AccountNotFound):
        service.transfer("missing", "a", "b", 2)
    with pytest.raises(InsufficientFunds):
        service.transfer("poor", "a", "a", 8)
    with pytest.raises(ValueError):
        service.transfer("invalid", "a", "a", 0)
    assert journal.entries == []
    assert requests.records == {}


def test_key_conflicts_cover_every_request_field():
    service, journal, _ = make_service({"a": 50, "b": 0, "c": 0})
    service.transfer("same", "a", "b", 10)
    for request in [("a", "b", 11), ("a", "c", 10), ("c", "b", 10)]:
        with pytest.raises(TransferConflict):
            service.transfer("same", *request)
    assert len(journal.entries) == 2
