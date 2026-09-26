import os
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from billing.api import create_app
from billing.contract_entrypoints import invoice_from_order_payload

pytestmark = pytest.mark.integration

REST = os.environ.get("ORDERS_REST_URL")
MOCK = os.environ.get("ORDERS_REST_MOCK_URL")
GRPC = os.environ.get("ORDERS_GRPC_ADDR")
DB = os.environ.get("REPORTS_DB_URL")
if not all([REST, MOCK, GRPC, DB]):
    pytest.skip("integration env vars not set", allow_module_level=True)


def wait_http(url: str, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            if httpx.get(url, timeout=2).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        if time.monotonic() > deadline:
            raise RuntimeError(f"{url} not ready after {timeout}s")
        time.sleep(1)


@pytest.fixture(scope="module")
def client() -> TestClient:
    wait_http(f"{REST}/health")
    wait_http(f"{MOCK}/health")
    return TestClient(create_app(orders_rest_url=REST, orders_grpc_addr=GRPC, reports_db_url=DB))


def test_invoice_paid_order(client):
    r = client.post("/invoices/o-1001")
    assert r.status_code == 201
    assert r.json() == {"order_id": "o-1001", "customer": "Ada Lovelace", "subtotal_minor": 1999,
                        "tax_minor": 165, "total_minor": 2164, "currency": "USD"}


def test_unpaid_order_is_not_invoiced(client):
    r = client.post("/invoices/o-1002")
    assert r.status_code == 409


def test_payment_status_uses_real_amount(client):
    r = client.get("/payments/o-1001/status")
    assert r.status_code == 200
    assert r.json() == {"order_id": "o-1001", "paid": True, "amount_minor": 1999, "currency": "USD"}


def test_revenue_report(client):
    r = client.get("/reports/revenue")
    assert r.status_code == 200
    assert r.json() == [{"day": "2026-09-01", "revenue_minor": 1999}, {"day": "2026-09-03", "revenue_minor": 12050}]


def test_rest_contract_examples_parse():
    paid = httpx.get(f"{MOCK}/orders/o-1001", headers={"Prefer": "example=paid"}, timeout=10).json()
    unpaid = httpx.get(f"{MOCK}/orders/o-1002", headers={"Prefer": "example=unpaid"}, timeout=10).json()
    assert invoice_from_order_payload(paid)["total_minor"] == 2164
    assert invoice_from_order_payload(unpaid) is None
