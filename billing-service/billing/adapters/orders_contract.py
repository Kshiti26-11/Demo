from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

@dataclass(frozen=True)
class OrderView:
    order_id: str
    customer_name: str
    amount_minor: int
    currency: str
    status: str
    created_at: Optional[str] = None

def normalize_status(value: str) -> str:
    if value.startswith("ORDER_STATUS_"):
        value = value[len("ORDER_STATUS_"):]
    return "AWAITING_PAYMENT" if value == "PENDING" else value

def from_rest(payload: dict) -> OrderView:
    customer = payload.get("customer", {})
    total = payload.get("total", {})
    
    return OrderView(
        order_id=payload["order_id"],
        customer_name=customer.get("display_name", payload.get("customer_name", "Unknown")),
        amount_minor=total.get("amount_minor", int(Decimal(str(payload.get("total_price", 0))) * 100)),
        currency=total.get("currency", "USD"),
        status=normalize_status(payload.get("status", "UNKNOWN")),
        created_at=payload.get("created_at")
    )

def from_summary(summary) -> OrderView:
    if summary.HasField("customer"):
        customer_name = summary.customer.display_name
    else:
        customer_name = summary.customer_name

    if summary.HasField("total"):
        amount_minor = summary.total.amount_minor
        currency = summary.total.currency
    else:
        amount_minor = int(Decimal(str(summary.total_price)) * 100)
        currency = "USD"
        
    status_enum = type(summary).DESCRIPTOR.fields_by_name["status"].enum_type
    status = status_enum.values_by_number[summary.status].name
    
    return OrderView(
        order_id=summary.order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=normalize_status(status),
        created_at=getattr(summary, "created_at", None)
    )
