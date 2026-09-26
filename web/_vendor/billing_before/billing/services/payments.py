from decimal import Decimal, ROUND_HALF_UP

PAID_STATES = {"ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def status_from_summary(summary) -> dict:
    field = type(summary).DESCRIPTOR.fields_by_name["status"]
    status_name = field.enum_type.values_by_number[summary.status].name

    amount_minor = _round_half_up(Decimal(str(summary.total_price)) * 100)

    return {
        "order_id": summary.order_id,
        "paid": status_name in PAID_STATES,
        "amount_minor": amount_minor,
        "currency": "USD",
    }
