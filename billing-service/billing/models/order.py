from datetime import datetime
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class OrderDTO(BaseModel):
    order_id: str
    customer_name: Optional[str] = None
    total_price: Optional[float] = None
    status: str
    created_at: datetime
    customer: Optional[Dict[str, Any]] = None
    total: Optional[Dict[str, Any]] = None
