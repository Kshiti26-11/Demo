from datetime import datetime
from typing import Optional

from pydantic import BaseModel, model_validator


class CustomerV2(BaseModel):
    """v2 nested customer object (Orders API v2)."""
    display_name: str
    id: Optional[str] = None


class MoneyV2(BaseModel):
    """v2 nested money object (Orders API v2)."""
    amount_minor: int       # integer minor units, e.g. 1999 for $19.99
    currency: str = "USD"


class OrderDTO(BaseModel):
    """Tolerant-reader DTO: accepts both Orders API v1 and v2 shapes."""

    order_id: str
    status: str
    created_at: datetime

    # --- v1 flat fields (kept optional for backward compat) ---
    customer_name: Optional[str] = None
    total_price: Optional[float] = None

    # --- v2 nested fields ---
    customer: Optional[CustomerV2] = None
    total: Optional[MoneyV2] = None

    # --- resolved convenience properties ---
    @property
    def display_name(self) -> str:
        """customer.display_name (v2) or customer_name (v1)."""
        if self.customer is not None:
            return self.customer.display_name
        return self.customer_name or ""

    @property
    def amount_minor(self) -> int:
        """total.amount_minor (v2) or round(total_price*100) (v1)."""
        if self.total is not None:
            return self.total.amount_minor
        if self.total_price is not None:
            from decimal import Decimal, ROUND_HALF_UP
            return int(
                Decimal(str(self.total_price)).mul_add(Decimal("100"), Decimal("0"))
                .quantize(Decimal("1"), rounding=ROUND_HALF_UP)
            )
        return 0

    @model_validator(mode="after")
    def _require_money(self) -> "OrderDTO":
        if self.customer is None and self.customer_name is None:
            raise ValueError("Order must have customer or customer_name")
        if self.total is None and self.total_price is None:
            raise ValueError("Order must have total or total_price")
        return self
