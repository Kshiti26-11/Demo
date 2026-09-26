from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

def normalize_status(value: str) -> str:
    if value.startswith("ORDER_STATUS_"):
        value = value[len("ORDER_STATUS_"):]
    if value == "PENDING":
        return "AWAITING_PAYMENT"
    return value

@dataclass(frozen=True)
class OrderView:
    order_id: str
    customer_name: str
    amount_minor: int
    currency: str
    status: str
    created_at: Optional[str] = None

def from_rest(payload: dict) -> OrderView:
    order_id = payload["order_id"]
    status = normalize_status(payload["status"])
    created_at = payload.get("created_at")

    if "customer" in payload and payload["customer"]:
        customer_name = payload["customer"]["display_name"]
    else:
        customer_name = payload.get("customer_name", "")

    if "total" in payload and payload["total"]:
        amount_minor = int(payload["total"]["amount_minor"])
        currency = payload["total"].get("currency", "USD")
    else:
        total_price = payload.get("total_price", 0)
        from decimal import ROUND_HALF_UP
        amount_minor = int(Decimal(str(total_price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 100)
        currency = "USD"

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
        created_at=created_at,
    )

def from_summary(summary) -> OrderView:
    order_id = summary.order_id
    enum_desc = type(summary).DESCRIPTOR.fields_by_name["status"].enum_type
    raw_status_name = enum_desc.values_by_number[summary.status].name
    status = normalize_status(raw_status_name)

    # Check HasField or attributes for v2 vs v1
    has_total = False
    try:
        has_total = summary.HasField("total")
    except ValueError:
        has_total = bool(getattr(summary, "total", None) and summary.total.amount_minor != 0)

    if has_total or (hasattr(summary, "total") and summary.total.amount_minor != 0):
        amount_minor = int(summary.total.amount_minor)
        currency = summary.total.currency or "USD"
    else:
        total_price = getattr(summary, "total_price", 0.0)
        from decimal import ROUND_HALF_UP
        amount_minor = int(Decimal(str(total_price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 100)
        currency = "USD"

    has_customer = False
    try:
        has_customer = summary.HasField("customer")
    except ValueError:
        has_customer = bool(getattr(summary, "customer", None) and summary.customer.display_name)

    if has_customer or (hasattr(summary, "customer") and summary.customer.display_name):
        customer_name = summary.customer.display_name
    else:
        customer_name = getattr(summary, "customer_name", "")

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
    )
