from decimal import Decimal, ROUND_HALF_UP
from billing.adapters.orders_contract import from_rest, OrderView

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"PENDING", "AWAITING_PAYMENT", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if isinstance(order, dict):
        order = from_rest(order)
    elif hasattr(order, "model_dump") or hasattr(order, "dict"):
        # Handle Pydantic OrderDTO
        d = order.model_dump() if hasattr(order, "model_dump") else order.dict()
        if "total" in d and d["total"]:
            amount_minor = int(d["total"]["amount_minor"])
            currency = d["total"]["currency"]
        else:
            total_price = d.get("total_price", 0.0)
            amount_minor = _round_half_up(Decimal(str(total_price)) * 100)
            currency = "USD"

        if "customer" in d and d["customer"]:
            customer_name = d["customer"]["display_name"]
        else:
            customer_name = d.get("customer_name", "")

        order = OrderView(
            order_id=d["order_id"],
            customer_name=customer_name,
            amount_minor=amount_minor,
            currency=currency,
            status=d["status"],
            created_at=str(d.get("created_at", "")),
        )

    if order.status in NOT_PAYABLE:
        return None

    subtotal = order.amount_minor
    tax = _round_half_up(Decimal(subtotal) * TAX_RATE)
    total = subtotal + tax

    return {
        "order_id": order.order_id,
        "customer": order.customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": order.currency,
    }
