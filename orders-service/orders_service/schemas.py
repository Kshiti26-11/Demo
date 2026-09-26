import datetime
from datetime import timezone as _tz
from typing import Optional

from pydantic import BaseModel


UTC = _tz.utc


def utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class CustomerOut(BaseModel):
    customer_id: str
    display_name: str


class MoneyOut(BaseModel):
    amount_minor: int
    currency: str


class OrderOut(BaseModel):
    order_id: str
    customer: CustomerOut
    total: MoneyOut
    status: str
    created_at: datetime.datetime
    shipping_eta: Optional[datetime.datetime] = None

    @classmethod
    def from_row(cls, row) -> "OrderOut":
        return cls(
            order_id=row.order_id,
            customer=CustomerOut(
                customer_id=row.customer_id,
                display_name=row.customer_display_name,
            ),
            total=MoneyOut(
                amount_minor=row.total_minor,
                currency=row.currency,
            ),
            status=row.status,
            created_at=utc(row.created_at),
            shipping_eta=utc(row.shipping_eta) if row.shipping_eta else None,
        )
