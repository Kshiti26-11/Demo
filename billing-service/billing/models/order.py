from datetime import datetime
from typing import Any, Optional
from pydantic import BaseModel, model_validator
from billing.adapters.orders_contract import from_rest


class OrderDTO(BaseModel):
    order_id: str
    customer_name: str
    amount_minor: int
    currency: str = "USD"
    status: str
    created_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def adapt_v1_v2(cls, data: Any) -> Any:
        if isinstance(data, dict):
            view = from_rest(data)
            dt = None
            if view.created_at:
                try:
                    dt = datetime.fromisoformat(view.created_at.replace("Z", "+00:00"))
                except Exception:
                    pass
            return {
                "order_id": view.order_id,
                "customer_name": view.customer_name,
                "amount_minor": view.amount_minor,
                "currency": view.currency,
                "status": view.status,
                "created_at": dt,
            }
        return data

