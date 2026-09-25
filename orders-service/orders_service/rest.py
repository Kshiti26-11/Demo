from typing import Optional

from fastapi import FastAPI, HTTPException

from . import config as _config
from .db import make_engine, make_sessionmaker
from .models import Base, Order
from .schemas import OrderOut
from . import seed as _seed_module


def create_app(
    database_url: Optional[str] = None,
    *,
    init_schema: bool = False,
    seed: bool = False,
) -> FastAPI:
    url = database_url or _config.database_url()
    engine = make_engine(url)
    if init_schema:
        Base.metadata.create_all(engine)
    Session = make_sessionmaker(engine)
    if seed:
        with Session() as s:
            _seed_module.seed(s)

    app = FastAPI(title="orders-service", version="1.0.0")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/orders", response_model=list[OrderOut])
    def list_orders():
        with Session() as s:
            rows = s.query(Order).order_by(Order.order_id).all()
            return [OrderOut.from_row(r) for r in rows]

    @app.get("/orders/{order_id}", response_model=OrderOut)
    def get_order(order_id: str):
        with Session() as s:
            row = s.get(Order, order_id)
            if row is None:
                raise HTTPException(status_code=404, detail="order not found")
            return OrderOut.from_row(row)

    return app
