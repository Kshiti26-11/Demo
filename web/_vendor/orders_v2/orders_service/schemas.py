from datetime import UTC, datetime
from pydantic import BaseModel, ConfigDict, field_serializer

def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    customer_id: str
    display_name: str

class MoneyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    amount_minor: int
    currency: str

class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    customer: CustomerOut
    total: MoneyOut
    status: str
    created_at: datetime
    shipping_eta: datetime | None = None

    @field_serializer("created_at", when_used="json-unless-none")
    def serialize_created_at(self, dt: datetime) -> str:
        return utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")

    @field_serializer("shipping_eta", when_used="json-unless-none")
    def serialize_shipping_eta(self, dt: datetime | None) -> str | None:
        if dt is None:
            return None
        return utc(dt).strftime("%Y-%m-%dT%H:%M:%SZ")

    @classmethod
    def from_row(cls, row) -> "OrderOut":
        return cls(
            order_id=row.order_id,
            customer=CustomerOut(
                customer_id=row.customer_id,
                display_name=row.customer_display_name,
            ),
            total=MoneyOut(
                amount_minor=int(row.total_minor),
                currency=row.currency,
            ),
            status=row.status,
            created_at=utc(row.created_at),
            shipping_eta=utc(row.shipping_eta) if row.shipping_eta else None,
        )
