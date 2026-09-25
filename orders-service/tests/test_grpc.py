import socket
import threading
import time

import grpc
import pytest

from orders_service.rest import create_app
from orders_service.grpc_server import serve
from orders_service.gen import orders_pb2, orders_pb2_grpc


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def grpc_channel():
    db_url = "sqlite+pysqlite:///:memory:"
    # Seed the database via rest.py so grpc_server shares same engine
    # Use a file-based SQLite so grpc_server can also access it
    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    file_url = f"sqlite:///{tmp.name}"

    # Init schema + seed via REST app
    create_app(file_url, init_schema=True, seed=True)

    port = _free_port()
    server = serve(port=port, db_url=file_url)

    channel = grpc.insecure_channel(f"127.0.0.1:{port}")
    stub = orders_pb2_grpc.OrderLookupStub(channel)

    yield stub, channel

    channel.close()
    server.stop(grace=0)
    try:
        os.unlink(tmp.name)
    except OSError:
        pass


def test_get_order_summary_paid(grpc_channel):
    stub, _ = grpc_channel
    resp = stub.GetOrderSummary(orders_pb2.GetOrderSummaryRequest(order_id="o-1001"))
    assert abs(resp.total_price - 19.99) < 0.001
    assert resp.customer_name == "Ada Lovelace"
    assert resp.status == orders_pb2.ORDER_STATUS_PAID


def test_get_order_not_found(grpc_channel):
    stub, _ = grpc_channel
    with pytest.raises(grpc.RpcError) as exc_info:
        stub.GetOrderSummary(orders_pb2.GetOrderSummaryRequest(order_id="o-9999"))
    assert exc_info.value.code() == grpc.StatusCode.NOT_FOUND
