from .models.order import OrderDTO
from .adapters.orders_contract import from_rest
from .services.invoice import build_invoice


def invoice_from_order_payload(payload: dict) -> dict | None:
    try:
        dto = OrderDTO.model_validate(payload)
        return build_invoice(dto)
    except Exception:
        view = from_rest(payload)
        return build_invoice(view)
