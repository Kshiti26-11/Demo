# Tolerant-reader rules for the Downstream Code Transformer

Goal: the consumer (billing-service) must work against the upstream Orders contract v1 AND v2 at the same time
(rolling deploys), with its own public API unchanged and the smallest possible diff.

## Hard rules
- Edit only files inside the consumer repository, on the syncsnitch/* branch you created. Never touch the upstream repo.
- Keep billing's endpoints and their request/response JSON exactly as they are.
- Minimal diff: no refactors, renames or reformatting outside the affected code. Never delete or weaken a test.
- If you change contracts/upstream/orders.proto, run `uv run python scripts/regen_stubs.py`.
- Finish with `uv run pytest -q` green in the consumer (integration tests are skipped locally; that is expected).

## Patterns (apply what impact.json needs)
1. REST -> create billing/adapters/__init__.py (empty) and billing/adapters/orders_contract.py with:
   - `normalize_status(value: str) -> str`: strip a leading "ORDER_STATUS_"; map "PENDING" -> "AWAITING_PAYMENT".
   - `@dataclass(frozen=True) class OrderView`: order_id, customer_name, amount_minor (int), currency, status, created_at=None.
   - `from_rest(payload: dict) -> OrderView`: use v2 fields when present (customer.display_name, total.amount_minor,
     total.currency), else v1 (customer_name, round-half-up(total_price x 100) via Decimal(str(x)), "USD").
   - `from_summary(summary) -> OrderView`: prefer summary.total / summary.customer when summary.HasField(...) is true,
     else the legacy total_price / customer_name; get the status name from the message descriptor
     (type(summary).DESCRIPTOR.fields_by_name["status"].enum_type.values_by_number[summary.status].name).
     This module must not import grpc or the generated stubs.
   Use OrderView wherever the old DTO or raw fields were used (services/invoice.py, services/payments.py,
   contract_entrypoints.py). After normalize_status the not-payable set is {"AWAITING_PAYMENT", "CANCELLED"} and the
   paid set is {"PAID", "SHIPPED"}.
2. gRPC -> replace contracts/upstream/orders.proto with the upstream v2 proto
   (`git -C ../orders-service show origin/feat/orders-v2:contracts/orders.proto`) BUT delete its two `reserved` lines and
   re-declare the removed fields with their ORIGINAL numbers and types:
       string customer_name = 2 [deprecated = true];
       double total_price = 3 [deprecated = true];
   Upstream only reserved those numbers, so this is wire-safe and one stub set reads both server versions.
   Then run scripts/regen_stubs.py.
3. SQL -> rename billing/reports/revenue.sql to revenue_v1.sql (unchanged) and add revenue_v2.sql:
       SELECT date(created_at) AS day, SUM(total_minor) AS revenue FROM orders
       WHERE status IN ('PAID', 'SHIPPED') GROUP BY day ORDER BY day
   In revenue.py first run `SELECT version_num FROM alembic_version`; use v2 when version_num >= "0002"
   (revenue is already minor units: int(revenue)); otherwise v1 (round-half-up(revenue x 100)). Same JSON output shape.
4. Fixtures/tests -> keep tests/fixtures/order_v1_*.json. Add tests/fixtures/order_v2_paid.json and order_v2_unpaid.json
   copied from the "paid" / "unpaid" examples of the upstream v2 openapi.yaml
   (`git -C ../orders-service show origin/feat/orders-v2:contracts/openapi.yaml`). Parametrize the unit tests over the v1 and
   v2 fixtures with identical expected results.
5. Write <consumer>/.syncsnitch.json exactly:
   {"upstream_repo": "kshiti26-11/orders-service", "upstream_pr": <PR_NUMBER>, "upstream_base": "main",
    "upstream_head": "feat/orders-v2", "run_id": "<RUN_ID>"}
6. Commit on the branch (do not push):
   git add -A && git commit -m "fix(contract): tolerant reader for Orders API v2 (SyncSnitch <RUN_ID>)" -m "Bob-Session: P3-3"
