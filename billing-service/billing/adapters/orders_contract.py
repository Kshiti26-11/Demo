from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


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
    created_at: Any = None


def from_rest(payload: dict) -> OrderView:
    order_id = payload["order_id"]
    status = normalize_status(payload.get("status", ""))
    created_at = payload.get("created_at")

    customer = payload.get("customer")
    if isinstance(customer, dict) and "display_name" in customer:
        customer_name = customer["display_name"]
    else:
        customer_name = payload.get("customer_name", "")

    total = payload.get("total")
    if isinstance(total, dict) and "amount_minor" in total:
        amount_minor = int(total["amount_minor"])
        currency = total.get("currency", "USD")
    else:
        total_price = payload.get("total_price", 0.0)
        amount_minor = _round_half_up(Decimal(str(total_price)) * 100)
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
    status_raw = field.enum_type.values_by_number[summary.status].name
    status = normalize_status(status_raw)

    if summary.HasField("customer"):
        customer_name = summary.customer.display_name
    else:
        customer_name = summary.customer_name

    if summary.HasField("total"):
        amount_minor = summary.total.amount_minor
        currency = summary.total.currency or "USD"
    else:
        amount_minor = _round_half_up(Decimal(str(summary.total_price)) * 100)
        currency = "USD"

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
    )
