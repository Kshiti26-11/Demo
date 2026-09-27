import json
from pathlib import Path

import pytest

from billing.contract_entrypoints import invoice_from_order_payload

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


PAID = _load("order_paid.json")
UNPAID = _load("order_unpaid.json")

EXPECTED = {
    "order_id": "o-1001",
    "customer": "Ada Lovelace",
    "subtotal_minor": 1999,
    "tax_minor": 165,
    "total_minor": 2164,
    "currency": "USD",
}


@pytest.mark.parametrize("filename", ["order_paid.json", "order_v2_paid.json"])
def test_paid_fixture_invoice(filename):
    payload = _load(filename)
    assert invoice_from_order_payload(payload) == EXPECTED


@pytest.mark.parametrize("filename", ["order_unpaid.json", "order_v2_unpaid.json"])
def test_unpaid_fixture_returns_none(filename):
    payload = _load(filename)
    assert invoice_from_order_payload(payload) is None


def test_cancelled_returns_none():
    payload = dict(PAID, status="CANCELLED")
    assert invoice_from_order_payload(payload) is None
