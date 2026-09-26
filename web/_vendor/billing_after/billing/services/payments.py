from decimal import Decimal, ROUND_HALF_UP
from ..adapters.orders_contract import from_summary

PAID_STATES = {"ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED", "PAID", "SHIPPED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def status_from_summary(summary) -> dict:
    view = from_summary(summary)

    return {
        "order_id": view.order_id,
        "paid": view.status in {"PAID", "SHIPPED"},
        "amount_minor": view.amount_minor,
        "currency": view.currency,
    }
