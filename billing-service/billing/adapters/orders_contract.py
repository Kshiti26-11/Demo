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

def from_rest(payload: dict) -> OrderView:
    order_id = payload.get("order_id") or payload.get("id", "")
    
    # customer
    customer = payload.get("customer")
    if isinstance(customer, dict):
        customer_name = customer.get("display_name", "")
    else:
        customer_name = payload.get("customer_name", "")

    # total / amount_minor
    total = payload.get("total")
    if isinstance(total, dict):
        amount_minor = int(total.get("amount_minor", 0))
        currency = total.get("currency", "USD")
    else:
        total_price = payload.get("total_price")
        if total_price is not None:
            d = Decimal(str(total_price)) * Decimal("100")
            amount_minor = int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        else:
            amount_minor = 0
        currency = payload.get("currency", "USD")

    status = normalize_status(payload.get("status", ""))
    created_at = payload.get("created_at")
    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
        created_at=created_at
    )

def from_summary(summary) -> OrderView:
    # check HasField or attributes
    has_total = False
    try:
        has_total = summary.HasField("total")
    except Exception:
        has_total = getattr(summary, "total", None) is not None

    if has_total and summary.total.amount_minor:
        amount_minor = summary.total.amount_minor
        currency = summary.total.currency or "USD"
    elif hasattr(summary, "total_price"):
        d = Decimal(str(summary.total_price)) * Decimal("100")
        amount_minor = int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        currency = "USD"
    else:
        amount_minor = 0
        currency = "USD"

    has_customer = False
    try:
        has_customer = summary.HasField("customer")
    except Exception:
        has_customer = getattr(summary, "customer", None) is not None

    if has_customer and summary.customer.display_name:
        customer_name = summary.customer.display_name
    elif hasattr(summary, "customer_name"):
        customer_name = summary.customer_name
    else:
        customer_name = ""

    # status enum name
    try:
        enum_values = type(summary).DESCRIPTOR.fields_by_name["status"].enum_type.values_by_number
        raw_status = enum_values[summary.status].name
    except Exception:
        raw_status = str(summary.status)

    status = normalize_status(raw_status)
    order_id = getattr(summary, "order_id", "")
    created_at = getattr(summary, "created_at", None)

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status,
        created_at=created_at
    )
