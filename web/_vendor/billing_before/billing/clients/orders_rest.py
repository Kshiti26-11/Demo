import httpx

class OrderNotFound(Exception):
    pass

class OrdersRestClient:
    def __init__(self, base_url: str, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url
        self.transport = transport

    async def get_order(self, order_id: str, headers: dict | None = None) -> dict:
        async with httpx.AsyncClient(base_url=self.base_url, transport=self.transport, timeout=10) as client:
            r = await client.get(f"/orders/{order_id}", headers=headers)
            if r.status_code == 404:
                raise OrderNotFound(f"order {order_id} not found")
            r.raise_for_status()
            return r.json()
