from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional


class CustomerDTO(BaseModel):
    customer_id: Optional[str] = None
    display_name: Optional[str] = None


class MoneyDTO(BaseModel):
    amount_minor: Optional[int] = None
    currency: Optional[str] = None


class OrderDTO(BaseModel):
    order_id: str
    customer_name: Optional[str] = None
    total_price: Optional[float] = None
    customer: Optional[CustomerDTO] = None
    total: Optional[MoneyDTO] = None
    status: str
    created_at: datetime
