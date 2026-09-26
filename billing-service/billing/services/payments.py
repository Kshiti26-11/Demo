from decimal import Decimal, ROUND_HALF_UP

PAID_STATES = {"PAID", "SHIPPED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def status_from_summary(summary) -> dict:
    from billing.adapters.orders_contract import from_summary
    view = from_summary(summary)

    amount_minor = view.amount_minor
    # If summary was initialized with total_price float directly in v1 style without round
    if hasattr(summary, "total_price") and summary.total_price != 0.0 and not summary.HasField("total"):
        amount_minor = _round_half_up(Decimal(str(summary.total_price)) * 100)

    return {
        "order_id": view.order_id,
        "paid": view.status in PAID_STATES,
        "amount_minor": amount_minor,
        "currency": view.currency,
    }
