import json
from pathlib import Path

import httpx
import pytest

from billing.api import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


PAID = _load("order_paid.json")
UNPAID = _load("order_unpaid.json")

EXPECTED_INVOICE = {
    "order_id": "o-1001",
    "customer": "Ada Lovelace",
    "subtotal_minor": 1999,
    "tax_minor": 165,
    "total_minor": 2164,
    "currency": "USD",
}


class MockTransport(httpx.MockTransport if hasattr(httpx, "MockTransport") else object):
    pass


def _make_mock_transport():
    """Build an httpx transport that returns fixtures or 404."""

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/orders/o-1001":
            return httpx.Response(200, json=PAID)
        elif path == "/orders/o-1002":
            return httpx.Response(200, json=UNPAID)
        else:
            return httpx.Response(404, json={"detail": "order not found"})

    return httpx.MockTransport(handler)


@pytest.fixture
def client():
    transport = _make_mock_transport()
    app = create_app(
        orders_rest_url="http://test",
        orders_rest_transport=transport,
    )
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_invoice_paid_order(client):
    r = client.post("/invoices/o-1001")
    assert r.status_code == 201
    assert r.json() == EXPECTED_INVOICE


def test_invoice_unpaid_order(client):
    r = client.post("/invoices/o-1002")
    assert r.status_code == 409


def test_invoice_unknown_order(client):
    r = client.post("/invoices/o-9999")
    assert r.status_code == 404
