import httpx


class OrderNotFound(Exception):
    pass


class OrdersRestClient:
    def __init__(self, base_url: str, transport=None):
        self._base_url = base_url
        self._transport = transport

    async def get_order(self, order_id: str, headers=None):
        async with httpx.AsyncClient(
            base_url=self._base_url,
            transport=self._transport,
            timeout=10,
        ) as client:
            r = await client.get(f"/orders/{order_id}", headers=headers)
            if r.status_code == 404:
                raise OrderNotFound(order_id)
            r.raise_for_status()
            return r.json()
