# P1-1 · orders-service v1 — Evidence Export

**Session:** P1-1  
**Person:** Person 1 (Upstream owner)  
**Branch:** main  
**Commit:** 15f95af  

---

## What was built

`orders-service` — upstream service that owns the Orders contract on three surfaces:

| Surface | File |
|---------|------|
| REST / OpenAPI 3.1 | `orders-service/contracts/openapi.yaml` |
| gRPC / Protobuf | `orders-service/contracts/orders.proto` |
| DB / Alembic migration | `orders-service/migrations/versions/0001_create_orders.py` |

### Source files created

```
orders_service/__init__.py
orders_service/config.py       — DATABASE_URL / GRPC_PORT env config
orders_service/db.py           — make_engine / make_sessionmaker
orders_service/models.py       — SQLAlchemy Order model (5 columns)
orders_service/seed.py         — loads seed.json, inserts 4 rows
orders_service/schemas.py      — Pydantic OrderOut + utc() helper
orders_service/rest.py         — FastAPI app factory (health / orders routes)
orders_service/grpc_server.py  — gRPC OrderLookup servicer + serve()
orders_service/gen/            — generated protobuf stubs (gen_proto.py)
```

### Tests

```
tests/test_rest.py        — 6 tests (health, list, get, 404, OpenAPI schema validation)
tests/test_grpc.py        — 2 tests (GetOrderSummary paid, NOT_FOUND)
tests/test_migrations.py  — 1 test (alembic upgrade head → column check)
```

## Acceptance result

```
9 passed, 3 warnings in 3.79s
```

All 9 tests passed (≥ 8 required). Docker skipped (not running in this environment).

## Commit

```
15f95af feat: orders-service v1 (REST + gRPC + DB contract)
        Bob-Session: P1-1
```
