from fastapi import FastAPI, HTTPException
from .config import database_url as get_db_url
from .db import make_engine, make_sessionmaker
from .models import Base, Order
from .schemas import OrderOut
from .seed import seed as run_seed

def create_app(database_url: str | None = None, *, init_schema: bool = False, seed: bool = False) -> FastAPI:
    url = database_url or get_db_url()
    engine = make_engine(url)
    if init_schema:
        Base.metadata.create_all(engine)
    Session = make_sessionmaker(engine)
    if seed:
        with Session() as s:
            run_seed(s)
    app = FastAPI(title="orders-service", version="2.0.0")
    app.state.Session = Session

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/orders", response_model=list[OrderOut], response_model_exclude_none=True)
    def list_orders():
        with app.state.Session() as s:
            rows = s.query(Order).order_by(Order.order_id).all()
            return [OrderOut.from_row(r) for r in rows]

    @app.get("/orders/{order_id}", response_model=OrderOut, response_model_exclude_none=True)
    def get_order(order_id: str):
        with app.state.Session() as s:
            row = s.query(Order).filter(Order.order_id == order_id).first()
            if row is None:
                raise HTTPException(status_code=404, detail="order not found")
            return OrderOut.from_row(row)

    return app
