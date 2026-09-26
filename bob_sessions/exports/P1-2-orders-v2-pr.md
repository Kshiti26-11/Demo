# P1-2 · orders-service v2 PR — Evidence Export

**Session:** P1-2
**Person:** Person 1 (Upstream owner)
**Branch:** feat/orders-v2
**Commit:** 6fed0d8
**Base:** main

---

## What was built

Breaking Orders API v2 — implements RFC-042.

### Contract changes

| Surface | Change |
|---------|--------|
| REST / OpenAPI 2.0.0 | `customer_name` → `customer {customer_id, display_name}`; `total_price` → `total {amount_minor, currency}`; `PENDING` → `AWAITING_PAYMENT`; optional `shipping_eta` added |
| gRPC / Protobuf | Fields 2,3 reserved; `Customer` + `Money` messages added; enum value 1 renamed `ORDER_STATUS_AWAITING_PAYMENT`; `shipping_eta` added |
| DB / Alembic 0002 | Adds `total_minor`, `currency`, `customer_id`, `shipping_eta`; renames `customer_name` → `customer_display_name`; drops `total_price`; data-migrates `PENDING` → `AWAITING_PAYMENT` |

### Files updated

```
contracts/openapi.yaml          — v2 REST contract
contracts/orders.proto          — v2 gRPC contract
migrations/versions/0002_...py  — Alembic migration (up + down)
docs/orders-v2-change-proposal.docx / .md
orders_service/gen/             — regenerated protobuf stubs
orders_service/models.py        — v2 columns
orders_service/seed.py          — uses status_v2, total_minor, customer_id, shipping_eta
orders_service/schemas.py       — CustomerOut, MoneyOut, OrderOut (nested)
orders_service/rest.py          — version=2.0.0, response_model_exclude_none=True
orders_service/grpc_server.py   — returns Customer, Money, shipping_eta
tests/test_rest.py              — 7 tests incl. shipping_eta + v2 OpenAPI validation
tests/test_grpc.py              — 2 tests: amount_minor, currency, display_name, status
tests/test_migrations.py        — upgrade 0001→0002 + downgrade with data assertions
```

## Acceptance result

```
10 passed, 4 warnings in 6.18s
```

## Commit

```
6fed0d8 feat!: Orders API v2 - money in minor units, structured customer, PENDING renamed AWAITING_PAYMENT
        Implements RFC-042 (docs/orders-v2-change-proposal.docx). Breaking for REST, gRPC and DB consumers.
        Bob-Session: P1-2
```

## PR

Branch `feat/orders-v2` pushed to `origin`. **PR must be opened manually** (`gh` CLI not installed):

```
URL: https://github.com/Kshiti26-11/Demo/compare/feat/orders-v2?expand=1
Title: feat!: Orders API v2 (money in minor units, customer object, AWAITING_PAYMENT)
Base: main  ←  Head: feat/orders-v2
Body:
  Implements RFC-042 (docs/orders-v2-change-proposal.docx).
  Breaking change for REST, gRPC and DB consumers.
  DO NOT MERGE - SyncSnitch demo trigger.
```

**NEVER MERGE PR #1.**
