from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import from_rest, normalize_status

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"PENDING", "AWAITING_PAYMENT", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    # Accept either OrderDTO, dict, or OrderView
    if hasattr(order, "dict") or isinstance(order, dict):
        d_payload = order.dict() if hasattr(order, "dict") else order
        view = from_rest(d_payload)
    elif hasattr(order, "customer_name") and hasattr(order, "amount_minor"):
        view = order
    else:
        # fallback or OrderDTO
        if isinstance(order, dict):
            view = from_rest(order)
        else:
            # OrderDTO instance
            d = order.model_dump() if hasattr(order, "model_dump") else order.dict()
            view = from_rest(d)

    if view.status in NOT_PAYABLE or normalize_status(view.status) in NOT_PAYABLE:
        return None

    subtotal = view.amount_minor
    tax = _round_half_up(Decimal(str(subtotal)) * TAX_RATE)
    total = subtotal + tax

    return {
        "order_id": view.order_id,
        "customer": view.customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": "USD",
    }
