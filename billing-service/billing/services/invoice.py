from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"PENDING", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if order.status in NOT_PAYABLE:
        return None

    subtotal = _round_half_up(Decimal(str(order.total_price)) * 100)
    tax = _round_half_up(Decimal(str(order.total_price)) * 100 * TAX_RATE)
    total = subtotal + tax

    return {
        "order_id": order.order_id,
        "customer": order.customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": "USD",
    }
