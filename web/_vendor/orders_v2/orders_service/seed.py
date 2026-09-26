import json
import datetime
from pathlib import Path

from .models import Order


_SEED_FILE = Path(__file__).parent / "seed.json"


def seed(session) -> None:
    session.query(Order).delete()
    data = json.loads(_SEED_FILE.read_text())
    for row in data["orders"]:
        eta_raw = row.get("shipping_eta")
        order = Order(
            order_id=row["order_id"],
            customer_id=row["customer_id"],
            customer_display_name=row["customer_name"],
            total_minor=row["amount_minor"],
            currency=row["currency"],
            status=row["status_v2"],
            created_at=datetime.datetime.fromisoformat(
                row["created_at"].replace("Z", "+00:00")
            ),
            shipping_eta=(
                datetime.datetime.fromisoformat(eta_raw.replace("Z", "+00:00"))
                if eta_raw
                else None
            ),
        )
        session.add(order)
    session.commit()


if __name__ == "__main__":
    from . import config
    from .db import make_engine, make_sessionmaker

    engine = make_engine(config.database_url())
    Session = make_sessionmaker(engine)
    with Session() as s:
        seed(s)
