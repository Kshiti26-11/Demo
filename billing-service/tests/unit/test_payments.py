import pytest

from billing.clients.gen import orders_pb2
from billing.services.payments import status_from_summary


def test_paid_order_summary():
    summary = orders_pb2.OrderSummary(
        order_id="o-1001",
        customer_name="Ada Lovelace",
        total_price=19.99,
        status=orders_pb2.ORDER_STATUS_PAID,
    )
    result = status_from_summary(summary)
    assert result == {
        "order_id": "o-1001",
        "paid": True,
        "amount_minor": 1999,
        "currency": "USD",
    }
