from decimal import Decimal, ROUND_HALF_UP

PAID_STATES = {"ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _resolve_amount_minor(summary) -> int:
    """Tolerant-reader: prefer v2 total.amount_minor, fall back to v1 total_price×100."""
    # v2 stubs: summary.total is a Money message with amount_minor
    total = getattr(summary, "total", None)
    if total is not None:
        amount = getattr(total, "amount_minor", None)
        if amount is not None:
            return int(amount)
    # v1 stubs: summary.total_price is a double (returns 0.0 when field is missing/reserved)
    total_price = getattr(summary, "total_price", 0.0)
    return _round_half_up(Decimal(str(total_price)) * 100)


def status_from_summary(summary) -> dict:
    field = type(summary).DESCRIPTOR.fields_by_name["status"]
    status_name = field.enum_type.values_by_number[summary.status].name

    amount_minor = _resolve_amount_minor(summary)

    return {
        "order_id": summary.order_id,
        "paid": status_name in PAID_STATES,
        "amount_minor": amount_minor,
        "currency": "USD",
    }
