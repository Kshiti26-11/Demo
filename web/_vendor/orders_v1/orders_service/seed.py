import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from sqlalchemy.orm import Session
from .config import database_url
from .db import make_engine, make_sessionmaker
from .models import Order

def seed(session: Session) -> None:
    session.query(Order).delete()
    seed_path = Path(__file__).parent / "seed.json"
    with open(seed_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    for item in data["orders"]:
        dt_str = item["created_at"].replace("Z", "+00:00")
        dt = datetime.fromisoformat(dt_str).astimezone(UTC)
        order = Order(
            order_id=item["order_id"],
            customer_name=item["customer_name"],
            total_price=Decimal(item["amount_minor"]) / Decimal(100),
            status=item["status_v1"],
            created_at=dt,
        )
        session.add(order)
    session.commit()

if __name__ == "__main__":
    engine = make_engine(database_url())
    SessionLocal = make_sessionmaker(engine)
    with SessionLocal() as s:
        seed(s)
