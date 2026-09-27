from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import from_summary

PAID_STATES = {"ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED", "PAID", "SHIPPED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def status_from_summary(summary) -> dict:
    view = from_summary(summary)
    
    field = type(summary).DESCRIPTOR.fields_by_name["status"]
    status_name = field.enum_type.values_by_number[summary.status].name

    return {
        "order_id": view.order_id,
        "paid": status_name in PAID_STATES or view.status in {"PAID", "SHIPPED"},
        "amount_minor": view.amount_minor,
        "currency": view.currency,
    }
