from .models.order import OrderDTO
from .services.invoice import build_invoice

def invoice_from_order_payload(payload: dict) -> dict | None:
    return build_invoice(OrderDTO.model_validate(payload))
