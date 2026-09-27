from datetime import datetime
from pydantic import BaseModel
from billing.adapters.orders_contract import normalize_status


class OrderDTO(BaseModel):
    order_id: str
    customer_name: str
    total_price: float
    status: str
    created_at: datetime

    @classmethod
    def model_validate(cls, obj, *args, **kwargs):
        if isinstance(obj, dict):
            from billing.adapters.orders_contract import from_rest
            view = from_rest(obj)
            return cls(
                order_id=view.order_id,
                customer_name=view.customer_name,
                total_price=float(view.amount_minor) / 100.0,
                status=view.status,
                created_at=datetime.fromisoformat(view.created_at.replace("Z", "+00:00")) if view.created_at else datetime.now(),
            )
        return super().model_validate(obj, *args, **kwargs)
