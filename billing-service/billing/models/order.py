from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MoneyDTO(BaseModel):
    amount_minor: int
    currency: str


class CustomerDTO(BaseModel):
    customer_id: str
    display_name: str


class OrderDTO(BaseModel):
    order_id: str
    customer_name: Optional[str] = None
    total_price: Optional[float] = None
    customer: Optional[CustomerDTO] = None
    total: Optional[MoneyDTO] = None
    status: str
    created_at: Optional[datetime] = None
    shipping_eta: Optional[datetime] = None
