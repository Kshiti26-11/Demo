from datetime import UTC, datetime
from pydantic import BaseModel, ConfigDict

def utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)

class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    order_id: str
    customer_name: str
    total_price: float
    status: str
    created_at: datetime

    @classmethod
    def from_row(cls, row) -> "OrderOut":
        return cls(
            order_id=row.order_id,
            customer_name=row.customer_name,
            total_price=float(row.total_price),
            status=row.status,
            created_at=utc(row.created_at),
        )
