from decimal import Decimal, ROUND_HALF_UP

PAID_STATES = {"ORDER_STATUS_PAID", "ORDER_STATUS_SHIPPED"}

def status_from_summary(summary) -> dict:
    status_name = type(summary).DESCRIPTOR.fields_by_name["status"].enum_type.values_by_number[summary.status].name
    amount_minor = int((Decimal(str(summary.total_price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "order_id": summary.order_id,
        "paid": status_name in PAID_STATES,
        "amount_minor": amount_minor,
        "currency": "USD",
    }
