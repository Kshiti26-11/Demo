from decimal import Decimal, ROUND_HALF_UP
from ..adapters.orders_contract import from_summary

PAID_STATES = {"PAID", "SHIPPED"}

def status_from_summary(summary) -> dict:
    order = from_summary(summary)
    
    return {
        "order_id": order.order_id,
        "paid": order.status in PAID_STATES,
        "amount_minor": order.amount_minor,
        "currency": order.currency,
    }
