from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal("0.0825")
# AWAITING_PAYMENT is the v2 rename of PENDING; keep PENDING for v1 backward compat.
NOT_PAYABLE = {"PENDING", "AWAITING_PAYMENT", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if order.status in NOT_PAYABLE:
        return None

    # Tolerant-reader: amount_minor resolves v2 total.amount_minor or v1 total_price×100.
    subtotal = order.amount_minor
    tax = _round_half_up(Decimal(subtotal) * TAX_RATE)
    total = subtotal + tax

    return {
        "order_id": order.order_id,
        "customer": order.display_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": "USD",
    }
