from .adapters.orders_contract import from_rest
from .services.invoice import build_invoice


def invoice_from_order_payload(payload: dict) -> dict | None:
    return build_invoice(from_rest(payload))
