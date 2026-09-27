import json
from pathlib import Path

import httpx
import pytest

from billing.api import create_app

FIXTURES = Path(__file__).parent.parent / "fixtures"


def _load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


EXPECTED_INVOICE = {
    "order_id": "o-1001",
    "customer": "Ada Lovelace",
    "subtotal_minor": 1999,
    "tax_minor": 165,
    "total_minor": 2164,
    "currency": "USD",
}


@pytest.mark.parametrize("paid_fixture,unpaid_fixture", [
    ("order_paid.json", "order_unpaid.json"),
    ("order_v2_paid.json", "order_v2_unpaid.json"),
])
def test_invoice_endpoints(paid_fixture, unpaid_fixture):
    paid = _load(paid_fixture)
    unpaid = _load(unpaid_fixture)

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/orders/o-1001":
            return httpx.Response(200, json=paid)
        elif path == "/orders/o-1002":
            return httpx.Response(200, json=unpaid)
        else:
            return httpx.Response(404, json={"detail": "order not found"})

    transport = httpx.MockTransport(handler)
    app = create_app(
        orders_rest_url="http://test",
        orders_rest_transport=transport,
    )
    from fastapi.testclient import TestClient
    client = TestClient(app)

    r = client.post("/invoices/o-1001")
    assert r.status_code == 201
    assert r.json() == EXPECTED_INVOICE

    r = client.post("/invoices/o-1002")
    assert r.status_code == 409

    r = client.post("/invoices/o-9999")
    assert r.status_code == 404
