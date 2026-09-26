"""Tests for trace: downstream consumer impact analysis."""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Fake billing consumer setup
# ---------------------------------------------------------------------------

_BILLING_MODELS_ORDER = """\
from typing import Optional

class Order:
    order_id: str
    customer_name: str
    total_price: float
    status: str

    def from_dict(self, d):
        self.order_id = d["order_id"]
        self.customer_name = d["customer_name"]
        self.total_price = d.get("total_price", 0.0)
        self.status = d["status"]
        return self
"""

_BILLING_SERVICES_INVOICE = """\
import httpx
from fastapi import APIRouter

router = APIRouter()

@router.post("/invoices/{order_id}")
async def create_invoice(order_id: str):
    resp = httpx.get(f"http://orders/orders/{order_id}")
    data = resp.json()
    if data["status"] == "PENDING":
        return {"invoice": "pending", "total": data["total_price"]}
    return {"invoice": "ok", "total": data["total_price"]}
"""

_BILLING_SERVICES_PAYMENTS = """\
import httpx
from fastapi import APIRouter

router = APIRouter()

@router.get("/payments/{order_id}/status")
async def payment_status(order_id: str):
    resp = httpx.get(f"http://orders/orders/{order_id}")
    order = resp.json()
    return {"total_price": order["total_price"], "paid": order["status"] == "PAID"}
"""

_BILLING_REPORTS_REVENUE_SQL = """\
-- Revenue report
SELECT order_id, total_price, status
FROM orders
WHERE status != 'PENDING'
ORDER BY total_price DESC;
"""


def _make_billing_consumer(tmpdir: Path) -> Path:
    """Create a fake billing consumer directory."""
    (tmpdir / "billing" / "models").mkdir(parents=True)
    (tmpdir / "billing" / "services").mkdir(parents=True)
    (tmpdir / "billing" / "reports").mkdir(parents=True)

    (tmpdir / "billing" / "models" / "order.py").write_text(
        _BILLING_MODELS_ORDER, encoding="utf-8"
    )
    (tmpdir / "billing" / "services" / "invoice.py").write_text(
        _BILLING_SERVICES_INVOICE, encoding="utf-8"
    )
    (tmpdir / "billing" / "services" / "payments.py").write_text(
        _BILLING_SERVICES_PAYMENTS, encoding="utf-8"
    )
    (tmpdir / "billing" / "reports" / "revenue.sql").write_text(
        _BILLING_REPORTS_REVENUE_SQL, encoding="utf-8"
    )
    return tmpdir


def _get_breaking_changes():
    """Return a minimal set of breaking changes from v1->v2."""
    return [
        {
            "id": "rest:Order.customer_name:property_removed",
            "surface": "rest",
            "kind": "property_removed",
            "location": "Order.customer_name",
            "old": "customer_name",
            "new": None,
            "breaking": True,
            "note": "",
        },
        {
            "id": "rest:Order.total_price:property_removed",
            "surface": "rest",
            "kind": "property_removed",
            "location": "Order.total_price",
            "old": "total_price",
            "new": None,
            "breaking": True,
            "note": "",
        },
        {
            "id": "rest:OrderStatus.PENDING:enum_value_removed",
            "surface": "rest",
            "kind": "enum_value_removed",
            "location": "OrderStatus.PENDING",
            "old": "PENDING",
            "new": None,
            "breaking": True,
            "note": "",
        },
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestTraceConsumer:
    def test_finds_hits_in_consumer(self):
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)
            assert len(hits) > 0, "Expected at least one hit"

    def test_hits_sorted_by_file_and_line(self):
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)
            pairs = [(h["file"], h["line"]) for h in hits]
            assert pairs == sorted(pairs), "Hits must be sorted by file, line"

    def test_models_order_links_to_post_invoices(self):
        """billing/models/order.py should link to POST /invoices/{order_id} via total_price."""
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)

            model_hits = [
                h for h in hits
                if "models/order.py" in h["file"]
            ]
            assert len(model_hits) > 0, "Expected hits in billing/models/order.py"

    def test_invoice_service_pending_linked_to_post_invoices(self):
        """billing/services/invoice.py should have PENDING hit linked to POST /invoices/{order_id}."""
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)

            invoice_hits = [
                h for h in hits
                if "services/invoice.py" in h["file"] and h["token"] == "PENDING"
            ]
            assert len(invoice_hits) > 0, (
                "Expected PENDING hit in billing/services/invoice.py"
            )
            endpoints_flat = [ep for h in invoice_hits for ep in h["endpoints"]]
            assert any("invoices" in ep for ep in endpoints_flat), (
                f"Expected POST /invoices/... endpoint, got: {endpoints_flat}"
            )

    def test_payments_service_total_price_linked_to_payments_endpoint(self):
        """billing/services/payments.py total_price should link to GET /payments/{order_id}/status."""
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)

            payment_hits = [
                h for h in hits
                if "services/payments.py" in h["file"] and h["token"] == "total_price"
            ]
            assert len(payment_hits) > 0, (
                "Expected total_price hit in billing/services/payments.py"
            )
            endpoints_flat = [ep for h in payment_hits for ep in h["endpoints"]]
            assert any("payments" in ep for ep in endpoints_flat), (
                f"Expected GET /payments/... endpoint, got: {endpoints_flat}"
            )

    def test_sql_total_price_hit(self):
        """billing/reports/revenue.sql should have total_price hit."""
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)

            sql_hits = [
                h for h in hits
                if h["file"].endswith(".sql") and h["token"] == "total_price"
            ]
            assert len(sql_hits) > 0, (
                "Expected total_price hit in revenue.sql"
            )

    def test_hit_shape(self):
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)

            required_keys = {
                "file", "line", "token", "change_ids", "usage_kind",
                "symbol", "endpoints", "in_tests"
            }
            for h in hits:
                assert required_keys <= set(h.keys()), f"Missing keys in hit: {h}"
                assert isinstance(h["in_tests"], bool)
                assert isinstance(h["endpoints"], list)
                assert isinstance(h["change_ids"], list)

    def test_skips_venv_and_pycache(self):
        from syncsnitch.trace import trace_consumer

        with tempfile.TemporaryDirectory() as tmpdir:
            consumer = _make_billing_consumer(Path(tmpdir))
            # Add a file in .venv
            venv_dir = consumer / ".venv" / "lib"
            venv_dir.mkdir(parents=True)
            (venv_dir / "order.py").write_text(
                "total_price = 99.0\ncustomer_name = 'test'\n", encoding="utf-8"
            )
            changes = _get_breaking_changes()
            hits = trace_consumer(changes, consumer)
            assert not any(".venv" in h["file"] for h in hits), \
                "Should not scan .venv"
