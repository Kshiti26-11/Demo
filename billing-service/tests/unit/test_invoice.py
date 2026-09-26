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


def test_paid_fixture_invoice():
    assert invoice_from_order_payload(PAID) == EXPECTED


def test_unpaid_fixture_returns_none():
    assert invoice_from_order_payload(UNPAID) is None


def test_cancelled_returns_none():
    payload = dict(PAID, status="CANCELLED")
    assert invoice_from_order_payload(payload) is None
