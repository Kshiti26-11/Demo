from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
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
        currency = payload["total"]["currency"]
    else:
        total_price = payload.get("total_price", 0.0)
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
    field = type(summary).DESCRIPTOR.fields_by_name["status"]
    raw_status_name = field.enum_type.values_by_number[summary.status].name
    status = normalize_status(raw_status_name)

    if summary.HasField("customer"):
        customer_name = summary.customer.display_name
    else:
        customer_name = getattr(summary, "customer_name", "")

    if summary.HasField("total"):
        amount_minor = summary.total.amount_minor
        currency = summary.total.currency or "USD"
    else:
        total_price = getattr(summary, "total_price", 0.0)
        amount_minor = int(Decimal(str(total_price)).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 100)
        currency = "USD"

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
    )
