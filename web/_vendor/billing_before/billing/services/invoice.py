from decimal import Decimal, ROUND_HALF_UP
from ..models.order import OrderDTO

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"PENDING", "CANCELLED"}

def build_invoice(order: OrderDTO) -> dict | None:
    if order.status in NOT_PAYABLE:
        return None
    subtotal = (Decimal(str(order.total_price)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    tax = (subtotal * TAX_RATE).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    total = subtotal + tax
    return {
        "order_id": order.order_id,
        "customer": order.customer_name,
        "subtotal_minor": int(subtotal),
        "tax_minor": int(tax),
        "total_minor": int(total),
        "currency": "USD",
    }
