from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import OrderView

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"AWAITING_PAYMENT", "CANCELLLD", "PENDING", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if isinstance(order, dict):
        from billing.adapters.orders_contract import from_rest
        order = from_rest(order)
    elif not isinstance(order, OrderView):
        # Maybe it's a model or something else with attributes
        pass

    status = getattr(order, "status", None)
    if status in NOT_PAYABLE:
        return None

    amount_minor = getattr(order, "amount_minor", None)
    if amount_minor is None:
        tp = getattr(order, "total_price", 0)
        amount_minor = _round_half_up(Decimal(str(tp)) * 100)

    subtotal = amount_minor
    tax = _round_half_up(Decimal(subtotal) * TAX_RATE)
    total = subtotal + tax

    customer_name = getattr(order, "customer_name", None)
    if customer_name is None and hasattr(order, "customer"):
        c = order.customer
        if isinstance(c, dict):
            customer_name = c.get("display_name", "")
        else:
            customer_name = getattr(c, "display_name", "")

    return {
        "order_id": getattr(order, "order_id", ""),
        "customer": customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": getattr(order, "currency", "USD"),
    }
