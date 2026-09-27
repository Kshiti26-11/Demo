from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import from_summary, OrderView

PAID_STATES = {"PAID", "SHIPPED", "ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED"}


def status_from_summary(summary) -> dict:
    view = from_summary(summary)

    return {
        "order_id": view.order_id,
        "paid": view.status in {"PAID", "SHIPPED"},
        "amount_minor": view.amount_minor,
        "currency": view.currency,
    }
