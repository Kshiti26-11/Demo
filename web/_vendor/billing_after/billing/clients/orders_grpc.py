class OrderNotFound(Exception):
    pass

def get_order_summary(addr: str, order_id: str):
    import grpc
    from .gen import orders_pb2, orders_pb2_grpc

    with grpc.insecure_channel(addr) as channel:
        stub = orders_pb2_grpc.OrderLookupStub(channel)
        try:
            return stub.GetOrderSummary(orders_pb2.GetOrderSummaryRequest(order_id=order_id), timeout=10)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise OrderNotFound(f"order {order_id} not found")
            raise
