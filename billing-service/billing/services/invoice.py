from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import from_rest

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"AWAITING_PAYMENT", "PENDING", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if isinstance(order, dict):
        view = from_rest(order)
    elif hasattr(order, "customer") and hasattr(order, "total"):
        # OrderDTO or OrderView
        view = order
    else:
        view = order

    status = getattr(view, "status", None)
    if status in NOT_PAYABLE:
        return None

    amount_minor = getattr(view, "amount_minor", None)
    if amount_minor is None:
        if hasattr(view, "total_price") and view.total_price is not None:
            amount_minor = _round_half_up(Decimal(str(view.total_price)) * 100)
        else:
            amount_minor = 0

    subtotal = amount_minor
    tax = _round_half_up(Decimal(str(subtotal)) * TAX_RATE)
    total = subtotal + tax

    customer_name = getattr(view, "customer_name", None)
    if not customer_name and hasattr(view, "customer") and view.customer:
        if isinstance(view.customer, dict):
            customer_name = view.customer.get("display_name")
        else:
            customer_name = getattr(view.customer, "display_name", None)

    return {
        "order_id": view.order_id,
        "customer": customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": getattr(view, "currency", "USD"),
    }
