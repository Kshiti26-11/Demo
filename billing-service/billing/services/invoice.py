from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import from_rest, OrderView

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"AWAITING_PAYMENT", "PENDING", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order_view: OrderView) -> dict | None:
    if order_view.status in NOT_PAYABLE:
        return None

    subtotal = order_view.amount_minor
    tax = _round_half_up(Decimal(subtotal) * TAX_RATE)
    total = subtotal + tax

    return {
        "order_id": order_view.order_id,
        "customer": order_view.customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": order_view.currency,
    }
