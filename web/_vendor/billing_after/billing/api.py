from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from . import config
from .clients import orders_grpc
from .clients.orders_rest import OrdersRestClient, OrderNotFound
from .contract_entrypoints import invoice_from_order_payload
from .reports.revenue import run_revenue_report
from .services.payments import status_from_summary

def create_app(
    orders_rest_url=None,
    orders_rest_transport=None,
    orders_grpc_addr=None,
    reports_db_url=None,
) -> FastAPI:
    rest_url = orders_rest_url or config.orders_rest_url()
    grpc_addr = orders_grpc_addr or config.orders_grpc_addr()
    db_url = reports_db_url or config.reports_db_url()

    rest_client = OrdersRestClient(base_url=rest_url, transport=orders_rest_transport)
    app = FastAPI(title="billing-service", version="1.0.0")

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/invoices/{order_id}", status_code=201)
    async def create_invoice(order_id: str):
        try:
            payload = await rest_client.get_order(order_id)
        except OrderNotFound:
            raise HTTPException(status_code=404, detail="order not found")
        invoice = invoice_from_order_payload(payload)
        if invoice is None:
            return JSONResponse(status_code=409, content={"detail": "order not payable"})
        return invoice

    @app.get("/payments/{order_id}/status")
    def get_payment_status(order_id: str):
        try:
            summary = orders_grpc.get_order_summary(grpc_addr, order_id)
        except orders_grpc.OrderNotFound:
            raise HTTPException(status_code=404, detail="order not found")
        return status_from_summary(summary)

    @app.get("/reports/revenue")
    def get_revenue():
        return run_revenue_report(db_url)

    return app
