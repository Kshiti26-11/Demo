from ..adapters.orders_contract import from_summary


def status_from_summary(summary) -> dict:
    view = from_summary(summary)
    PAID_STATES = {"PAID", "SHIPPED"}

    return {
        "order_id": view.order_id,
        "paid": view.status in PAID_STATES,
        "amount_minor": view.amount_minor,
        "currency": view.currency,
    }
