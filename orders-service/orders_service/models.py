from sqlalchemy import String, BigInteger, DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
from typing import Optional
import datetime


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_id: Mapped[str] = mapped_column(String(32), nullable=False)
    customer_display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    total_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    shipping_eta: Mapped[Optional[datetime.datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
