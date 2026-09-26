# billing-service

Downstream billing consumer for the SyncSnitch demo.
Intentionally breaks when orders-service changes from v1 to v2.

## Endpoints

- `GET  /health`                   — liveness probe
- `POST /invoices/{order_id}`      — create invoice (201), 409 if not payable, 404 if unknown
- `GET  /payments/{order_id}/status` — payment status via gRPC
- `GET  /reports/revenue`          — daily revenue report from replica DB

## Contract dependencies (v1)

- `contracts/upstream/openapi.yaml`  — REST shape (orders-service v1)
- `contracts/upstream/orders.proto`  — gRPC shape (orders-service v1)
- `billing/clients/gen/`            — generated protobuf stubs

## Run tests

```
uv run pytest -q
```

## Docker integration test

Requires the SyncSnitch verification containers to be running.
Build the image: `docker build -t billing-service:tests .`
Integration tests are skipped locally unless env vars are set.
