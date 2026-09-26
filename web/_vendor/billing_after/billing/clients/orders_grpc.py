class OrderNotFound(Exception):
    pass


def get_order_summary(addr: str, order_id: str):
    import grpc
    from .gen import orders_pb2, orders_pb2_grpc

    channel = grpc.insecure_channel(addr)
    try:
        stub = orders_pb2_grpc.OrderLookupStub(channel)
        request = orders_pb2.GetOrderSummaryRequest(order_id=order_id)
        try:
            return stub.GetOrderSummary(request, timeout=10)
        except grpc.RpcError as e:
            if e.code() == grpc.StatusCode.NOT_FOUND:
                raise OrderNotFound(order_id)
            raise
    finally:
        channel.close()
