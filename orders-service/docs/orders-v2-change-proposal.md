# RFC-042: Orders API v2 — money in minor units, structured customer, payment-state rename

| | |
|---|---|
| **Owner** | Orders team (orders-service) |
| **Status** | Approved for rollout |
| **Affects** | REST `GET /orders/{order_id}`, gRPC `orders.OrderLookup/GetOrderSummary`, database table `orders` |
| **Known consumers** | billing-service (invoices, payment status, revenue report) |

## 1. Summary
Orders v2 changes how an order's money, customer and payment state are represented. The REST payload, the gRPC `OrderSummary` message and the `orders` table all change in the same release (PR "Orders API v2").

## 2. Motivation
1. **Float money caused rounding incidents.** Invoices built from `total_price: 19.99` were off by one cent after tax in two incidents. Money must be integer minor units plus an ISO 4217 currency.
2. **Customer identity.** Consumers need a stable `customer_id`, not only a display name.
3. **Clearer payment state.** `PENDING` was read as "pending shipment" by some teams. The new name is `AWAITING_PAYMENT`.

## 3. Detailed changes
| ID | Surface | v1 | v2 | Consumer impact |
|---|---|---|---|---|
| CH1 | REST + gRPC + DB | `total_price` (decimal major units, e.g. 19.99) | `total { amount_minor: 1999, currency: "USD" }` (gRPC: `Money total = 6`; DB: `total_minor` + `currency`) | **Breaking**: field removed |
| CH2 | REST + gRPC + DB | `customer_name` | `customer { customer_id, display_name }` (gRPC: `Customer customer = 5`; DB: `customer_display_name` + `customer_id`) | **Breaking**: field moved |
| CH3 | REST + gRPC + DB | status `PENDING` | status `AWAITING_PAYMENT` (gRPC enum value 1 renamed, same number) | **Breaking**: value renamed. A consumer that treats `PENDING` as "not payable" will silently treat unpaid orders as payable |
| CH4 | REST + gRPC + DB | — | optional `shipping_eta` (RFC 3339) | Non-breaking: additive |
| MIG | DB | migration `0001` | migration `0002_money_customer_status` | Readers of `orders.total_price` / `orders.customer_name` break |

gRPC notes: fields 2 (`customer_name`) and 3 (`total_price`) are **removed and reserved**. Their numbers will never be reused, so a consumer may keep reading them from old servers during the rollout.

## 4. Compatibility
v2 is **not** backward compatible for consumers. Old clients get no error, just missing data. Old REST clients fail on the missing `total_price`. Old gRPC clients read `total_price` as `0.0`, which is silent. Old SQL reports fail on the dropped column.

## 5. Rollout plan
1. Consumers ship **tolerant readers** that accept v1 and v2 at the same time (see §6).
2. Orders deploys v2 (migration `0002` runs at deploy).
3. After one week, consumers remove the v1 code paths in a cleanup PR.

## 6. Migration guidance for consumers
- **REST:** read `total.amount_minor` when present, else `round(total_price * 100)`. Read `customer.display_name` when present, else `customer_name`. Treat both `PENDING` and `AWAITING_PAYMENT` as "not payable".
- **gRPC:** vendor the v2 proto but **re-declare fields 2 and 3** as `[deprecated = true]` in your copy, so one set of stubs can read both server versions. Prefer `total` / `customer` when `HasField(...)` is true.
- **SQL:** check `alembic_version.version_num`. Use `SUM(total_price)` for `0001` and `SUM(total_minor)` for `0002`.
- Keep your own public API unchanged.

## 7. Open questions
- Should `shipping_eta` become required once all carriers report it? (Not in v2.)

## 8. Approvals
Orders lead ✅ · Platform architecture ✅ · Billing lead ⏳ (needs a companion change before rollout)
