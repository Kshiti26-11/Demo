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
    order_id = payload.get("order_id")
    status = normalize_status(payload.get("status", ""))
    
    # customer
    customer = payload.get("customer")
    if isinstance(customer, dict):
        customer_name = customer.get("display_name", "")
    else:
        customer_name = payload.get("customer_name", "")

    # total / amount_minor
    total = payload.get("total")
    if isinstance(total, dict) and "amount_minor" in total:
        amount_minor = int(total["amount_minor"])
        currency = total.get("currency", "USD")
    else:
        total_price = payload.get("total_price", 0)
        d = Decimal(str(total_price)) * 100
        amount_minor = int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        currency = "USD"

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
    order_id = summary.order_id
    field = type(summary).DESCRIPTOR.fields_by_name["status"]
    raw_status = field.enum_type.values_by_number[summary.status].name
    status = normalize_status(raw_status)

    if summary.HasField("total") and summary.total.amount_minor != 0 or hasattr(summary, "total") and summary.total.amount_minor is not None:
        # Check if total is populated or HasField
        try:
            has_total = summary.HasField("total")
        except Exception:
            has_total = summary.total is not None and (summary.total.amount_minor != 0 or summary.total.currency != "")
        
        if has_total:
            amount_minor = int(summary.total.amount_minor)
            currency = summary.total.currency or "USD"
        else:
            d = Decimal(str(summary.total_price)) * 100
            amount_minor = int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            currency = "USD"
    else:
        d = Decimal(str(summary.total_price)) * 100
        amount_minor = int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        currency = "USD"

    try:
        has_customer = summary.HasField("customer")
    except Exception:
        has_customer = summary.customer is not None and summary.customer.display_name != ""

    if has_customer:
        customer_name = summary.customer.display_name
    else:
        customer_name = summary.customer_name

    return OrderView(
        order_id=order_id,
        customer_name=customer_name,
        amount_minor=amount_minor,
        currency=currency,
        status=status
    )
