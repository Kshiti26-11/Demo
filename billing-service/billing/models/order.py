from datetime import datetime
from pydantic import BaseModel, Field


class OrderDTO(BaseModel):
    order_id: str
    customer_name: str = Field(default="")
    total_price: float = Field(default=0.0)
    status: str
    created_at: datetime
