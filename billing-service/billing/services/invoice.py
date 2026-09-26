from decimal import Decimal, ROUND_HALF_UP

TAX_RATE = Decimal("0.0825")
NOT_PAYABLE = {"PENDING", "AWAITING_PAYMENT", "CANCELLED"}


def _round_half_up(d: Decimal) -> int:
    return int(d.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def build_invoice(order) -> dict | None:
    if hasattr(order, "status"):
        status = order.status
        order_id = order.order_id
        customer_name = getattr(order, "customer_name", None)
        if not customer_name and hasattr(order, "customer") and order.customer:
            customer_name = order.customer.display_name

        amount_minor = getattr(order, "amount_minor", None)
        if amount_minor is None and hasattr(order, "total") and order.total:
            amount_minor = order.total.amount_minor
        if amount_minor is None and hasattr(order, "total_price") and order.total_price is not None:
            amount_minor = _round_half_up(Decimal(str(order.total_price)) * 100)

        currency = getattr(order, "currency", "USD")
        if currency == "USD" and hasattr(order, "total") and order.total and hasattr(order.total, "currency"):
            currency = order.total.currency
    else:
        # dict
        from billing.adapters.orders_contract import from_rest
        view = from_rest(order)
        status = view.status
        order_id = view.order_id
        customer_name = view.customer_name
        amount_minor = view.amount_minor
        currency = view.currency

    if status in NOT_PAYABLE:
        return None

    subtotal = amount_minor
    tax = _round_half_up(Decimal(str(subtotal)) * TAX_RATE)
    total = subtotal + tax

    return {
        "order_id": order_id,
        "customer": customer_name,
        "subtotal_minor": subtotal,
        "tax_minor": tax,
        "total_minor": total,
        "currency": currency,
    }
