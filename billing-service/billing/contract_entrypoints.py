from billing.models.order import OrderDTO
from billing.services.invoice import build_invoice


def invoice_from_order_payload(payload: dict) -> dict | None:
    return build_invoice(OrderDTO.model_validate(payload))
