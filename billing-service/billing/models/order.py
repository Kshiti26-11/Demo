from datetime import datetime
from pydantic import BaseModel


class OrderDTO(BaseModel):
    order_id: str
    customer_name: str | None = None
    total_price: float | None = None
    customer: dict | None = None
    total: dict | None = None
    status: str
    created_at: datetime
