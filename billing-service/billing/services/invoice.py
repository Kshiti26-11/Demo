from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"PENDING", "AWAITING_PAYMENT", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if order.status in NOT_PAYABLE:
        return None

    if hasattr(order, "amount_minor"):
        subtotal = order.amount_minor
        currency = getattr(order, "currency", "USD")
    elif hasattr(order, "total_price"):
        subtotal = _round_half_up(Decimal(str(order.total_price)) * 100)
        currency = getattr(order, "currency", "USD")
    else:
        subtotal = 0
        currency = "USD"

    tax = _round_half_up(Decimal(str(subtotal)) * TAX_RATE)
    total = subtotal + tax

    customer_name = getattr(order, "customer_name", "")

    return {
        "order_id": order.order_id,
        "customer": customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": currency,
    }
