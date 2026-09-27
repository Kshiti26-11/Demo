from .models.order import OrderDTO
from .services.invoice import build_invoice
from .adapters.orders_contract import from_rest


def invoice_from_order_payload(payload: dict) -> dict | None:
    view = from_rest(payload)
    return build_invoice(view)
