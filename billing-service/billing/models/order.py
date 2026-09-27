from datetime import datetime
from pydantic import BaseModel, Field
from billing.adapters.orders_contract import normalize_status


class CustomerDTO(BaseModel):
    customer_id: str
    display_name: str


class MoneyDTO(BaseModel):
    amount_minor: int
    currency: str


class OrderDTO(BaseModel):
    order_id: str
    customer_name: str | None = None
    total_price: float | None = None
    customer: CustomerDTO | None = None
    total: MoneyDTO | None = None
    status: str
    created_at: datetime | None = None

    def model_post_init(self, __context) -> None:
        object.__setattr__(self, "status", normalize_status(self.status))
        if self.customer and not self.customer_name:
            object.__setattr__(self, "customer_name", self.customer.display_name)
        if self.total and self.total_price is None:
            object.__setattr__(self, "total_price", self.total.amount_minor / 100.0)
