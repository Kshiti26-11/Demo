import pytest

from billing.clients.gen import orders_pb2
from billing.services.payments import status_from_summary


def test_paid_order_summary_v1_compat():
    """Tolerant-reader backward compat: old-style summary object with total_price float."""

    class _SummaryV1:
        """Stand-in for v1 generated OrderSummary proto message (before stub regen)."""
        DESCRIPTOR = orders_pb2.OrderSummary.DESCRIPTOR

        def __init__(self):
            self.order_id = "o-1001"
            self.total_price = 19.99
            self.status = orders_pb2.ORDER_STATUS_PAID

    result = status_from_summary(_SummaryV1())
    assert result == {
        "order_id": "o-1001",
        "paid": True,
        "amount_minor": 1999,
        "currency": "USD",
    }


def test_paid_order_summary_v2_stubs():
    """v2 stubs: OrderSummary has total (Money) with amount_minor."""
    summary = orders_pb2.OrderSummary(
        order_id="o-1001",
        status=orders_pb2.ORDER_STATUS_PAID,
        customer=orders_pb2.Customer(display_name="Ada Lovelace", id="c-1"),
        total=orders_pb2.Money(amount_minor=1999, currency="USD"),
    )
    result = status_from_summary(summary)
    assert result == {
        "order_id": "o-1001",
        "paid": True,
        "amount_minor": 1999,
        "currency": "USD",
    }
