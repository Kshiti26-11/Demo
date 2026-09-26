import datetime
from datetime import timezone as _tz

from pydantic import BaseModel


UTC = _tz.utc


def utc(dt: datetime.datetime) -> datetime.datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class OrderOut(BaseModel):
    order_id: str
    customer_name: str
    total_price: float
    status: str
    created_at: datetime.datetime

    model_config = {"json_encoders": {datetime.datetime: lambda v: v.strftime("%Y-%m-%dT%H:%M:%SZ")}}

    @classmethod
    def from_row(cls, row) -> "OrderOut":
        return cls(
            order_id=row.order_id,
            customer_name=row.customer_name,
            total_price=float(row.total_price),
            status=row.status,
            created_at=utc(row.created_at),
        )
