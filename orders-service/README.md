# orders-service

Upstream Orders service — the canonical owner of the Orders contract for the SyncSnitch demo.

## Contract surfaces

| Surface | File |
|---------|------|
| REST / OpenAPI | `contracts/openapi.yaml` |
| gRPC / Protobuf | `contracts/orders.proto` |
| DB / Alembic | `migrations/versions/0001_create_orders.py` |

## Run tests

```bash
uv run pytest -q
```

## Local run

```bash
uv run uvicorn orders_service.rest:create_app --factory --reload
```
