from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


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
    created_at: str = None


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def from_rest(payload: dict) -> OrderView:
    order_id = payload["order_id"]
    status = normalize_status(payload["status"])
    created_at = payload.get("created_at")

    if "customer" in payload and isinstance(payload["customer"], dict):
        customer_name = payload["customer"].get("display_name")
    else:
        customer_name = payload.get("customer_name")

    if "total" in payload and isinstance(payload["total"], dict):
        total_dict = payload["total"]
        amount_minor = total_dict["amount_minor"]
        currency = total_dict.get("currency", "USD")
    else:
        tp = payload.get("total_price", 0)
        amount_minor = _round_half_up(Decimal(str(tp)) * 100)
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
    raw_status = field.enum_type.values_by_number[summary.status].name
    status = normalize_status(raw_status)

    if summary.HasField("customer") and summary.customer.HasField("display_name") or getattr(summary, "customer", None) and summary.customer.display_name:
        customer_name = summary.customer.display_name
    elif hasattr(summary, "customer_name") and summary.customer_name:
        customer_name = summary.customer_name
    else:
        customer_name = getattr(summary.customer, "display_name", "")

    if summary.HasField("total"):
        amount_minor = summary.total.amount_minor
        currency = summary.total.currency or "USD"
    elif hasattr(summary, "total_price") and summary.total_price:
        amount_minor = _round_half_up(Decimal(str(summary.total_price)) * 100)
        currency = "USD"
    else:
        amount_minor = 0
        currency = "USD"

    shipping_eta = getattr(summary, "shipping_eta", None)

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
    )
