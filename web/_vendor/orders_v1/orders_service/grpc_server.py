from concurrent.futures import ThreadPoolExecutor

import grpc

from . import config as _config
from .db import make_engine, make_sessionmaker
from .models import Order
from .gen import orders_pb2, orders_pb2_grpc


class OrderLookup(orders_pb2_grpc.OrderLookupServicer):
    def __init__(self, session_factory):
        self._Session = session_factory

    def GetOrderSummary(self, request, context):
        with self._Session() as s:
            row = s.get(Order, request.order_id)
        if row is None:
            context.abort(grpc.StatusCode.NOT_FOUND, "order not found")
            return
        return orders_pb2.OrderSummary(
            order_id=row.order_id,
            customer_name=row.customer_name,
            total_price=float(row.total_price),
            status=orders_pb2.OrderStatus.Value("ORDER_STATUS_" + row.status),
        )


def serve(port=None, db_url=None):
    url = db_url or _config.database_url()
    engine = make_engine(url)
    Session = make_sessionmaker(engine)

    server = grpc.server(ThreadPoolExecutor(max_workers=8))
    orders_pb2_grpc.add_OrderLookupServicer_to_server(OrderLookup(Session), server)
    server.add_insecure_port(f"0.0.0.0:{port or _config.grpc_port()}")
    server.start()
    return server


if __name__ == "__main__":
    serve().wait_for_termination()
