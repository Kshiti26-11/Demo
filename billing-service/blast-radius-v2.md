# billing-service v2 Blast-Radius Analysis

## POST /invoices/{order_id}
- **Contract surface:** REST
- **File:line:** `billing/models/order.py:6-7`, `billing/services/invoice.py:13`
- **Severity:** LOUD
- **Why:** v2 drops `customer_name` and `total_price`, replacing them with `customer.display_name` and `total.amount_minor`; Pydantic validation raises `ValidationError` → HTTP 500.

## GET /payments/{order_id}/status
- **Contract surface:** gRPC
- **File:line:** `billing/services/payments.py:14`
- **Severity:** SILENT
- **Why:** v2 `OrderSummary` reserves and removes fields 2 (`customer_name`) and 3 (`total_price`); old stubs silently read `summary.total_price` as `0.0`, so `amount_minor` is always **0** with no error.

## GET /reports/revenue
- **Contract surface:** DB
- **File:line:** `billing/reports/revenue.sql:1`
- **Severity:** LOUD
- **Why:** Migration `0002` drops the `total_price` column; `SUM(total_price)` raises a DB error → HTTP 500.

## The bug a human fixing only the loud errors would still miss
`billing/services/invoice.py:4` — `NOT_PAYABLE = {"PENDING", "CANCELLED"}` — after the migration renames `PENDING` → `AWAITING_PAYMENT`, formerly-unpaid orders silently pass the payability check and get invoiced.
