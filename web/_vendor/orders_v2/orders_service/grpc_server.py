from concurrent.futures import ThreadPoolExecutor
from datetime import UTC
import grpc
from .config import database_url as get_db_url, grpc_port
from .db import make_engine, make_sessionmaker
from .gen import orders_pb2, orders_pb2_grpc
from .models import Order

class OrderLookup(orders_pb2_grpc.OrderLookupServicer):
    def __init__(self, Session):
        self.Session = Session

    def GetOrderSummary(self, request, context):
        with self.Session() as s:
            row = s.query(Order).filter(Order.order_id == request.order_id).first()
            if row is None:
                context.abort(grpc.StatusCode.NOT_FOUND, "order not found")
            status_enum = orders_pb2.OrderStatus.Value("ORDER_STATUS_" + row.status)
            shipping_eta_str = ""
            if row.shipping_eta:
                dt = row.shipping_eta
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=UTC)
                else:
                    dt = dt.astimezone(UTC)
                shipping_eta_str = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

            return orders_pb2.OrderSummary(
                order_id=row.order_id,
                status=status_enum,
                customer=orders_pb2.Customer(
                    customer_id=row.customer_id,
                    display_name=row.customer_display_name,
                ),
                total=orders_pb2.Money(
                    amount_minor=int(row.total_minor),
                    currency=row.currency,
                ),
                shipping_eta=shipping_eta_str,
            )

def serve(port: int | None = None, db_url: str | None = None) -> grpc.Server:
    url = db_url or get_db_url()
    engine = make_engine(url)
    Session = make_sessionmaker(engine)
    server = grpc.server(ThreadPoolExecutor(max_workers=8))
    orders_pb2_grpc.add_OrderLookupServicer_to_server(OrderLookup(Session), server)
    p = port or grpc_port()
    server.add_insecure_port(f"0.0.0.0:{p}")
    server.start()
    return server

if __name__ == "__main__":
    serve().wait_for_termination()
