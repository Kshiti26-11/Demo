from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, model_validator


class CustomerDTO(BaseModel):
    customer_id: str
    display_name: str


class MoneyDTO(BaseModel):
    amount_minor: int
    currency: str


class OrderDTO(BaseModel):
    order_id: str
    customer_name: Optional[str] = None
    total_price: Optional[float] = None
    customer: Optional[CustomerDTO] = None
    total: Optional[MoneyDTO] = None
    status: str
    created_at: datetime

    @model_validator(mode="before")
    @classmethod
    def compat_v1_v2(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "customer" in data and isinstance(data["customer"], dict):
                data.setdefault("customer_name", data["customer"].get("display_name", ""))
            elif "customer_name" in data and data["customer_name"]:
                data.setdefault("customer", {"customer_id": "c-0000", "display_name": data["customer_name"]})

            if "total" in data and isinstance(data["total"], dict):
                amount_minor = data["total"].get("amount_minor", 0)
                data.setdefault("total_price", amount_minor / 100.0)
            elif "total_price" in data and data["total_price"] is not None:
                from decimal import Decimal, ROUND_HALF_UP
                minor = int(Decimal(str(data["total_price"])).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * 100)
                data.setdefault("total", {"amount_minor": minor, "currency": "USD"})
        return data
