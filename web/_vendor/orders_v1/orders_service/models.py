from sqlalchemy import String, Numeric, DateTime
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped
import decimal
import datetime


class Base(DeclarativeBase):
    pass


class Order(Base):
    __tablename__ = "orders"

    order_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(200), nullable=False)
    total_price: Mapped[decimal.Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
