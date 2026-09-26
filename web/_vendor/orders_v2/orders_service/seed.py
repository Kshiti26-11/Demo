import json
from datetime import UTC, datetime
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
        shipping_eta = None
        if item.get("shipping_eta"):
            s_str = item["shipping_eta"].replace("Z", "+00:00")
            shipping_eta = datetime.fromisoformat(s_str).astimezone(UTC)
        order = Order(
            order_id=item["order_id"],
            customer_id=item["customer_id"],
            customer_display_name=item["customer_name"],
            total_minor=item["amount_minor"],
            currency=item["currency"],
            status=item["status_v2"],
            created_at=dt,
            shipping_eta=shipping_eta,
        )
        session.add(order)
    session.commit()

if __name__ == "__main__":
    engine = make_engine(database_url())
    SessionLocal = make_sessionmaker(engine)
    with SessionLocal() as s:
        seed(s)
